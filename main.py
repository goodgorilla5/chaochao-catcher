import requests
from bs4 import BeautifulSoup
import os
from datetime import datetime

class AmisGitHubRobot:
    def __init__(self):
        self.url = "https://amis.afa.gov.tw/download/DownloadVegFruitCoopData2.aspx"
        self.session = requests.Session()
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'
        }

    def get_taiwan_date(self):
        """ 自動生成民國日期 """
        now = datetime.now()
        # 2026年是民國115年
        tw_year = now.year - 1911
        return f"{tw_year}/{now.strftime('%m/%d')}"

    def fetch_hidden_params(self):
        """ 自動從網頁抓取最新的通關密碼 (ViewState) """
        print("🔍 正在獲取網頁權杖...")
        r = self.session.get(self.url, headers=self.headers)
        soup = BeautifulSoup(r.text, 'html.parser')
        
        return {
            'vs': soup.find('input', {'id': '__VIEWSTATE'})['value'],
            'gen': soup.find('input', {'id': '__VIEWSTATEGENERATOR'})['value'],
            'val': soup.find('input', {'id': '__EVENTVALIDATION'})['value']
        }

    def execute_download(self):
        date_str = self.get_taiwan_date()
        params = self.fetch_hidden_params()
        
        payload = {
            '__EVENTTARGET': 'ctl00$contentPlaceHolder$lbtnDownload',
            '__VIEWSTATE': params['vs'],
            '__VIEWSTATEGENERATOR': params['gen'],
            '__EVENTVALIDATION': params['val'],
            'ctl00$contentPlaceHolder$txtStartDate': date_str,
            'ctl00$contentPlaceHolder$txtEndDate': date_str,
            'ctl00$contentPlaceHolder$txtSupplyNo': 'A00013 台北市農會',
            'ctl00$contentPlaceHolder$hfldSupplyNo': 'A00013'
        }

        print(f"📡 正在請求日期：{date_str} 的資料...")
        resp = self.session.post(self.url, data=payload, headers=self.headers)
        
        if resp.status_code == 200:
            # 建立 data 資料夾存放檔案
            if not os.path.exists('data'): os.makedirs('data')
            
            filename = f"data/market_{date_str.replace('/', '')}.txt"
            with open(filename, "wb") as f:
                f.write(resp.content)
            print(f"✨ 成功！檔案已儲存至 {filename}")
        else:
            print(f"❌ 失敗，狀態碼：{resp.status_code}")

if __name__ == "__main__":
    bot = AmisGitHubRobot()
    bot.execute_download()