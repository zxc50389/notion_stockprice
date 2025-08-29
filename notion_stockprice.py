import requests
from notion_client import Client
from datetime import datetime
import os
import logging

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

    def get_stock_prices_batch(symbols):
        """一次查多檔股票價格"""
        url = "https://api.twelvedata.com/time_series"
        params = {
            "symbol": ",".join(symbols),
            "interval": "1day",
            "outputsize": 2,
            "apikey": API_KEY
        }
        try:
            resp = requests.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            results = {}
            for sym in symbols:
                if sym in data and "values" in data[sym] and len(data[sym]["values"]) > 0:
                    results[sym] = float(data[sym]["values"][0]["close"])
                else:
                    logger.warning(f"Twelve Data 沒有回傳 {sym} 的收盤價。")
            return results
        except Exception as e:
            logger.error(f"批次獲取股價時出錯: {e}")
            return {}

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

    # 🔥 一次最多查 8 檔（依 Twelve Data 免費版限制）
    batch_size = 8
    for i in range(0, len(stocks), batch_size):
        batch = stocks[i:i+batch_size]
        symbols = [s["symbol"] for s in batch]
        logger.info(f"處理第 {i//batch_size + 1} 批股票，共 {len(batch)} 支")

        prices = get_stock_prices_batch(symbols)
        for stock in batch:
            price = prices.get(stock["symbol"])
            update_stock_price(stock["id"], price, stock["symbol"])

    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    send_telegram_message(f"所有股票價格已更新完成！更新時間：{current_time}")

    return {"statusCode": 200, "body": "所有股票價格已更新完成"}
