import os
from dotenv import load_dotenv
load_dotenv()

import ccxt
import pytz
import requests
from datetime import datetime, timedelta

# 取引所のインスタンスを作成
bitbank_reference = ccxt.bitbank({
    'apiKey': os.environ['PRICE_API_KEY'],
    'secret': os.environ['PRICE_SECRET'],
})

# LINE Notifyの設定
line_notify_api = os.environ['LINE_NOTIFY_API']
line_notify_token = os.environ['LINE_NOTIFY_TOKEN']

# 通貨ペアと日付の設定
symbol = 'MATIC/JPY'

# 日本時間のタイムゾーンを設定
jst = pytz.timezone('Asia/Tokyo')

# 日本時間で今日の0時0分を取得
now_jst = datetime.now(jst)
start_of_yesterday_jst = (now_jst - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)

# sinceをUTC時間のタイムスタンプに変換
since = bitbank_reference.parse8601(start_of_yesterday_jst.isoformat())
print(since)  # 日本時間の今日の0時0分に対応するUTC時間のタイムスタンプ

# 自分の取引履歴を取得
my_trades = bitbank_reference.fetch_my_trades(symbol, since=since)

# 移動平均コストと総量を追跡する変数
average_cost = 0
total_amount = 0

# 売却益計算のための変数
total_sell_profit = 0

# 取引データから移動平均コストと売却益を計算
for trade in my_trades:
    if trade['side'] == 'buy':
        # 移動平均コストの更新
        new_total_amount = total_amount + trade['amount']
        average_cost = (average_cost * total_amount + trade['cost']) / new_total_amount
        total_amount = new_total_amount
    elif trade['side'] == 'sell' and total_amount > 0:
        # 売却益の計算（売却価格 - 移動平均コスト）
        sell_profit = (trade['price'] - average_cost) * trade['amount']
        total_sell_profit += sell_profit

        # 売却後の総量の更新
        total_amount -= trade['amount']
        if total_amount <= 0:
            total_amount = 0
            average_cost = 0  # 全部売却したので平均コストをリセット

# 売却益の表示
print(f"Total sell profit: {total_sell_profit:.2f} {symbol}")

# LINEに送信するメッセージの設定
headers = {'Authorization': f'Bearer {line_notify_token}'}
message = f'今日の収益: {total_sell_profit:.2f} JPY'

# LINE Notify経由でメッセージを送信
response = requests.post(line_notify_api, headers=headers, data={'message': message})

# 応答の確認
print(response.status_code)
