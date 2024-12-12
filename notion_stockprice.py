import requests
from notion_client import Client
from dotenv import load_dotenv
import os

# 載入 .env 文件中的環境變數
load_dotenv()

# 股市 API 設置
STOCK_API_URL = os.getenv("STOCK_API_URL")
API_KEY = os.getenv("API_KEY")

# Notion API 設置
notion = Client(auth=os.getenv("NOTION_API_TOKEN"))
DATABASE_ID = os.getenv("DATABASE_ID")

# 從環境變數中讀取排除關鍵字，並轉換為列表
exclude_keywords = os.getenv("EXCLUDE_KEYWORDS", "").split(",")

# 獲取 Notion 資料庫中股票代碼
def get_stock_symbols():
    stocks = []
    response = notion.databases.query(database_id=DATABASE_ID)
    for page in response["results"]:
        properties = page["properties"]
        if "Stock" in properties and properties["Stock"]["type"] == "title":
            stock_title = properties["Stock"]["title"]
            if stock_title:  # 確保有內容
                stock_symbol = stock_title[0]["text"]["content"]
                
                # 檢查股票名稱是否包含排除的關鍵字
                if any(keyword in stock_symbol for keyword in exclude_keywords):
                    print(f"跳過 {stock_symbol}，因為名稱包含排除關鍵字。")
                    continue

                stocks.append({"id": page["id"], "symbol": stock_symbol})
    return stocks

# 從股市 API 獲取股價
def get_stock_price(symbol):
    params = {
        "function": "TIME_SERIES_INTRADAY",
        "symbol": symbol,
        "interval": "1min",
        "apikey": API_KEY
    }
    response = requests.get(STOCK_API_URL, params=params)
    try:
        data = response.json()
        # 確認返回的數據是否包含預期內容
        if "Time Series (1min)" in data:
            latest_time = list(data["Time Series (1min)"].keys())[0]
            return float(data["Time Series (1min)"][latest_time]["1. open"])
        else:
            print(f"API 回應錯誤: {data.get('Note', '未知原因')}")
            return None
    except Exception as e:
        print(f"獲取 {symbol} 股價時出現錯誤: {e}")
        return None

# 更新 Notion 資料庫中的價格
def update_stock_price(page_id, price):
    if price is not None:
        try:
            notion.pages.update(
                page_id=page_id,
                properties={
                    "Price": {"number": price}  # 假設資料庫中有 "Price" 欄位
                }
            )
            print(f"已更新 Page {page_id} 的股價為 {price}")
        except Exception as e:
            print(f"更新 Page {page_id} 時出現錯誤: {e}")
    else:
        print(f"跳過更新 Page {page_id}，因為未取得有效股價。")

# 主程式
def main():
    stocks = get_stock_symbols()
    if not stocks:
        print("未在資料庫中找到任何股票代碼。")
        return

    for stock in stocks:
        print(f"正在獲取 {stock['symbol']} 的股價...")
        price = get_stock_price(stock["symbol"])
        update_stock_price(stock["id"], price)

if __name__ == "__main__":
    main()