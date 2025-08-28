import requests
from notion_client import Client
from datetime import datetime
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging

def lambda_handler(event, context):
    # 設定 logging
    logging.basicConfig(level=logging.DEBUG, force=True)
    logger = logging.getLogger(__name__)

    # 環境變數設置
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

    def get_stock_price(symbol):
        """用 Twelve Data API 獲取每日收盤價"""
        url = "https://api.twelvedata.com/time_series"
        params = {
            "symbol": symbol,
            "interval": "1day",
            "outputsize": 2,  # 取前兩天，以確保抓到最新交易日收盤價
            "apikey": API_KEY
        }
        try:
            resp = requests.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            if "values" in data and len(data["values"]) > 0:
                # 最新一個交易日收盤價
                return float(data["values"][0]["close"])
            else:
                logger.warning(f"Twelve Data 沒有回傳 {symbol} 的收盤價。")
        except Exception as e:
            logger.error(f"獲取 {symbol} 收盤價時出現錯誤: {e}")
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
                logger.debug(f"更新結果: {response}")
            except Exception as e:
                logger.error(f"更新 Page {page_id}（{stock_symbol}）時出現錯誤: {e}")
        else:
            logger.info(f"跳過更新 Page {page_id}（{stock_symbol}），因為未取得有效股價。")

    stocks = get_stock_symbols()
    if not stocks:
        logger.info("未在資料庫中找到任何股票代碼。")
        return {"statusCode": 200, "body": "未找到股票代碼"}

    # 限制並行數量，避免 Twelve Data 429
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {executor.submit(get_stock_price, stock["symbol"]): stock for stock in stocks}
        for future in as_completed(futures):
            stock = futures[future]
            try:
                price = future.result()
                update_stock_price(stock["id"], price, stock["symbol"])
            except Exception as e:
                logger.error(f"處理 {stock['symbol']} 時出現錯誤: {e}")

    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    send_telegram_message(f"所有股票價格已更新完成！更新時間：{current_time}")

    return {"statusCode": 200, "body": "所有股票價格已更新完成"}
