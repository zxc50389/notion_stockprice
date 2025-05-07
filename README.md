# notion_stockprice
Follow the steps below to correctly populate the configuration file with the required values:

1. **STOCK_API_URL**:  
   This is the URL endpoint for the stock API you want to use. For example, if you are using Alpha Vantage, set this as:  
   ```plaintext
   https://www.alphavantage.co/query
   ```

2. **API_KEY**:  
   This is the unique API key provided by Alpha Vantage. To get your API key:  
   - Go to [Alpha Vantage's website](https://www.alphavantage.co/).
   - Sign up for an account or log in.
   - Locate your API key in the account settings or dashboard.
   Replace `your alphavantage key` with your actual API key.

3. **NOTION_API_TOKEN**:  
   This is the integration token for Notion. To get your Notion API token:  
   - Go to [Notion's API documentation](https://developers.notion.com/).
   - Create a new integration in your Notion workspace.
   - Copy the integration token and replace `your NOTION_API_TOKEN` with it.

4. **DATABASE_ID**:  
   This is the unique ID of the database in your Notion workspace that you want to interact with. To find your database ID:  
   - Open the database in Notion.
   - Copy the URL of the database.
   - The part of the URL after `/database/` (and before any `?` or `#`) is your `DATABASE_ID`.
   Replace `the DATABASE_ID` with the actual ID of your database.

5. **EXCLUDE_KEYWORDS**:  
   This is a comma-separated list of keywords that you want to exclude during filtering or processing. For example, if you want to exclude results with "loan" or "debt," you would write:  
   ```plaintext
   loan,debt
   ```
   Replace `any don't want key word` with the keywords you want to filter out.

### Example Configuration
Here’s an example of a completed configuration file:  
```plaintext
STOCK_API_URL = "https://www.alphavantage.co/query"
API_KEY = "ABCDEFG123456789"
NOTION_API_TOKEN = "secret_xxxxyyyyzzzz"
DATABASE_ID = "abc12345"
EXCLUDE_KEYWORDS = "loan,debt"
```

Make sure to save this configuration securely and do not share your API keys publicly.
