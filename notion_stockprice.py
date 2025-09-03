import requests
from notion_client import Client
from datetime import datetime
import os
import logging
import time

def lambda_handler(event, context):
    logging.basicConfig(level=logging.DEBUG, force=True)
    logger = logging.getLogger(__name__)

    REQUIRED_ENV_VARS = ["BOT_TOKEN", "CHAT_ID", "API_KEY", "NOTION_API_TOKEN", "DATABASE_ID"]
    missing_vars = [var for var in REQUIRED_ENV_VARS if not os.getenv(var)]
    if missing_vars:
        raise EnvironmentError(f"缺少以下必要環境變數：{', '.join(missing_vars)}")

    BOT_TOKEN = os.getenv("BOT_TOKEN")
    CHAT_ID = os.getenv("CHAT_ID")
    TELEGRAM_API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    API_KEY = os.getenv("API_KEY")  # Twelve Data API Key
    NOTION_API_TOKEN = os.getenv("NOTION_API_TOKEN")
    DATABASE_ID = os.getenv("DATABASE_ID")
    EXCLUDE_KEYWORDS = os.getenv("EXCLUDE_KEYWORDS", "").split(",")

    notion = None
    api_call_count = 0  # 追蹤 API 呼叫次數
    api_call_start_time = time.time()  # 記錄開始時間
    
    def get_notion_client():
        nonlocal notion
        if notion is None:
            notion = Client(auth=NOTION_API_TOKEN)
        return notion

    def send_telegram_message(message):
        payload = {"chat_id": CHAT_ID, "text": message}
        try:
            response = requests.post(TELEGRAM_API_URL, data=payload)
            response.raise_for_status()
            logger.info(f"Telegram 通知發送成功: {message}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Telegram 通知發送失敗: {e}")

    def check_rate_limit():
        """檢查並處理 API 速率限制"""
        nonlocal api_call_count, api_call_start_time
        current_time = time.time()
        
        # 如果已經過了一分鐘，重置計數器
        if current_time - api_call_start_time >= 60:
            api_call_count = 0
            api_call_start_time = current_time
            logger.info("API 速率限制計數器已重置")
        
        # 如果達到限制，等待到下一分鐘
        if api_call_count >= 7:  # 保守一點，用 7 而不是 8
            wait_time = 61 - (current_time - api_call_start_time)
            if wait_time > 0:
                logger.info(f"達到 API 速率限制，等待 {wait_time:.1f} 秒...")
                time.sleep(wait_time)
                api_call_count = 0
                api_call_start_time = time.time()

    def get_stock_symbols():
        stocks = []
        try:
            notion_client = get_notion_client()
            has_more = True
            start_cursor = None

            while has_more:
                response = notion_client.databases.query(
                    database_id=DATABASE_ID,
                    start_cursor=start_cursor
                )
                for page in response["results"]:
                    properties = page["properties"]
                    if "Stock" in properties and properties["Stock"]["type"] == "title":
                        stock_title = properties["Stock"]["title"]
                        if stock_title:
                            stock_symbol = stock_title[0]["text"]["content"]
                            if any(keyword in stock_symbol for keyword in EXCLUDE_KEYWORDS):
                                logger.info(f"跳過 {stock_symbol}，因為名稱包含排除關鍵字。")
                                continue
                            stocks.append({"id": page["id"], "symbol": stock_symbol})
                has_more = response.get("has_more", False)
                start_cursor = response.get("next_cursor")
        except Exception as e:
            logger.error(f"獲取股票代碼時出現錯誤: {e}")
        logger.debug(f"取得的股票資料: {stocks}")
        return stocks

    def get_single_stock_price(symbol, retry_count=0):
        """獲取單一股票價格，含重試機制"""
        nonlocal api_call_count
        
        if retry_count >= 3:
            logger.error(f"重試 3 次後仍無法取得 {symbol} 的股價")
            return None
            
        check_rate_limit()
        
        url = "https://api.twelvedata.com/time_series"
        params = {
            "symbol": symbol,
            "interval": "1day",
            "outputsize": 2,
            "apikey": API_KEY
        }
        
        logger.debug(f"呼叫 Twelve Data API 查詢單一股票: {symbol}")
        try:
            resp = requests.get(url, params=params)
            api_call_count += 1
            logger.info(f"API 呼叫次數: {api_call_count} (查詢 {symbol})")
            
            resp.raise_for_status()
            data = resp.json()
            logger.debug(f"{symbol} API 回應: {data}")
            
            # 檢查各種錯誤情況
            if "message" in data:
                if "rate limit" in data["message"].lower():
                    logger.warning(f"收到速率限制錯誤 ({symbol})，等待後重試...")
                    time.sleep(65)
                    api_call_count = 0
                    api_call_start_time = time.time()
                    return get_single_stock_price(symbol, retry_count + 1)
                elif "invalid" in data["message"].lower() or "not found" in data["message"].lower():
                    logger.error(f"{symbol}: {data['message']}")
                    return None
                else:
                    logger.warning(f"{symbol} API 警告: {data['message']}")
            
            if "values" in data and data["values"] and len(data["values"]) > 0:
                price = float(data["values"][0]["close"])
                logger.info(f"成功取得 {symbol} 股價: {price}")
                return price
            else:
                logger.error(f"{symbol}: 沒有找到股價數據")
                return None
                
        except requests.exceptions.RequestException as e:
            logger.error(f"網路錯誤 - {symbol}: {e}")
            if retry_count < 2:
                time.sleep(5)
                return get_single_stock_price(symbol, retry_count + 1)
            return None
        except Exception as e:
            logger.error(f"獲取 {symbol} 股價時出錯: {e}")
            return None

    def update_stock_price(page_id, price, stock_symbol):
        if price is not None:
            try:
                notion_client = get_notion_client()
                response = notion_client.pages.update(
                    page_id=page_id,
                    properties={"Price": {"number": price}}
                )
                logger.info(f"已更新 Page {page_id} 的股價（{stock_symbol}）為 {price}")
            except Exception as e:
                logger.error(f"更新 Page {page_id}（{stock_symbol}）時出現錯誤: {e}")
        else:
            logger.info(f"跳過更新 Page {page_id}（{stock_symbol}），因為未取得有效股價。")

    stocks = get_stock_symbols()
    if not stocks:
        logger.info("未在資料庫中找到任何股票代碼。")
        return {"statusCode": 200, "body": "未找到股票代碼"}

    all_results = []  # 用來收集所有股票與價格

    # 🔥 改為逐一處理每支股票，提供更詳細的診斷
    total_stocks = len(stocks)
    logger.info(f"開始逐一處理 {total_stocks} 支股票...")
    
    for i, stock in enumerate(stocks, 1):
        logger.info(f"=== 處理第 {i}/{total_stocks} 支股票: {stock['symbol']} ===")
        
        price = get_single_stock_price(stock['symbol'])
        update_stock_price(stock["id"], price, stock["symbol"])
        
        if price is not None:
            all_results.append((stock["symbol"], price))
        else:
            all_results.append((stock["symbol"], None))
        
        # 每支股票後稍作休息，避免過於頻繁
        if i < total_stocks:
            logger.info(f"休息 2 秒後繼續...")
            time.sleep(2)

    # 照股票代碼排序
    all_results.sort(key=lambda x: x[0])

    # 組訊息，加入失敗原因分析
    result_lines = []
    valid_prices = 0
    failed_stocks = []
    
    for symbol, price in all_results:
        if price is not None:
            result_lines.append(f"✅ {symbol}: ${price:.2f}")
            valid_prices += 1
        else:
            result_lines.append(f"❌ {symbol}: 無法取得價格")
            failed_stocks.append(symbol)

    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 建議檢查失敗的股票代號
    suggestion = ""
    if failed_stocks:
        suggestion = f"\n\n💡 可能原因：\n• 股票代號錯誤\n• 市場休市\n• API 權限不足\n" \
                    f"失敗股票：{', '.join(failed_stocks[:5])}"
        if len(failed_stocks) > 5:
            suggestion += f" 等 {len(failed_stocks)} 支"
    
    message = f"📊 股票價格更新完成！\n" \
              f"✅ 成功更新: {valid_prices}/{len(all_results)} 支\n" \
              f"❌ 失敗: {len(failed_stocks)} 支\n\n" \
              + "\n".join(result_lines) \
              + suggestion \
              + f"\n\n⏰ 更新時間：{current_time}"
    send_telegram_message(message)

    return {"statusCode": 200, "body": f"股票價格更新完成，成功 {valid_prices}/{len(all_results)} 支"}
