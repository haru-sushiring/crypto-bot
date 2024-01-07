import os
from dotenv import load_dotenv
load_dotenv()

import ccxt
import calendar
import pandas as pd
import numpy as np
import math
import time
from collections import defaultdict

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# BitbankのAPIに接続
bitbank_price = ccxt.bitbank({
    'apiKey': os.environ['PRICE_API_KEY'],
    'secret': os.environ['PRICE_SECRET'],
})
bitbank_trade = ccxt.bitbank({
    'apiKey': os.environ['TRADE_API_KEY'],
    'secret': os.environ['TRADE_SECRET'],
})

# 1分前のコードが動いていたら停止
lock_file = os.environ['LOCK_FILE_PATH']
if os.path.exists(lock_file):
    print("Script is already running.")
    exit()

#開始前にロックファイル作成
open(lock_file, 'w').close()


def update_env_file(env_path, key, value):
    """ .env ファイルを更新するヘルパー関数 """
    lines = []
    with open(env_path, 'r') as file:
        for line in file:
            if line.startswith(key):
                lines.append(f"{key}={value}\n")
            else:
                lines.append(line)
    with open(env_path, 'w') as file:
        file.writelines(lines)


def orders_merge(open_orders, symbol, params, amount = ''):
    # 同じ価格での注文を追跡するための辞書
    orders_at_same_price = defaultdict(list)

    for order in open_orders:
        # 同じ価格での注文を辞書に追加
        orders_at_same_price[order['price']].append(order)

    # print(orders_at_same_price)
    for price, orders in orders_at_same_price.items():
        if len(orders) > 2:
            #　3個以上の場合、1個まで減らす
            # すべての注文をキャンセル
            for order in orders:
                bitbank_trade.cancel_order(order['id'], symbol)

            if orders[0]['side'] == 'buy':
                bitbank_trade.create_limit_buy_order(symbol, amount, price, params)
            else:
                bitbank_trade.create_limit_sell_order(symbol, amount, price, params)
        elif len(orders) > 1:
            # 2個以上の注文をまとめる
            # まず、全注文の合計量を計算
            total_amount = sum(float(order['amount']) for order in orders)

            # すべての注文をキャンセル
            for order in orders:
                bitbank_trade.cancel_order(order['id'], symbol)

            # 新しい合計注文を作成
            if orders[0]['side'] == 'buy':
                bitbank_trade.create_limit_buy_order(symbol, total_amount, price, params)
            else:
                bitbank_trade.create_limit_sell_order(symbol, total_amount, price, params)


def execute_trade(current_rsi, current_price, buy_price, buy_flg, sell_price, sell_flg):
    now = datetime.now(ZoneInfo("Asia/Tokyo"))
    symbol = 'MATIC/JPY'  # トレードしたい通貨ペア
    amount = 5  # 購入したいMATICの量
    params = {
        'post_only': True,
    }

    open_orders = bitbank_price.fetch_open_orders(symbol)
    print(len(open_orders))
    # 同時発注制限件数(30件)を回避するために同じ注文をまとめる
    if len(open_orders) > 10:
        orders_merge(open_orders, symbol, params)

    # for order in open_orders:
    #     if order['side'] == 'sell' and float(order['price']) > current_price:
    #         # 注文価格が現在の市場買い価格より高い場合、注文を取り消し
    #         response = bitbank_trade.cancel_order(order['id'], symbol)
    #         print(response)

    # has_buy_order = any(order['side'] == 'buy' for order in open_orders)
    # has_sell_order = any(order['side'] == 'sell' for order in open_orders)
    # if has_buy_order:
    #     buy_flg = True
    # else:
    #     buy_flg = False
    # if has_sell_order:
    #     sell_flg = True
    # else:
    #     sell_flg = False
    #     # sell_price = 0
    #     # buy_price = 0

    balance = bitbank_price.fetch_balance()
    jpy_balance = balance['JPY']['free']
    matic_balance = balance['MATIC']['free']
    print(f"jpy_balance:{jpy_balance}")
    print(f"matic_balance{matic_balance}")

    if current_rsi > 70 and matic_balance >= amount:
        # RSIが70を超え、かつ既に購入していたら売り
        price = (math.floor(current_price * 10) / 10) + 0.5
        if sell_price == price:
            price += 0.1
        # if sell_flg:
        #     price + 0.3
        # if (current_price - current_price) >= 0.5:
        #     price = current_price + 1
        # else:
        #     price = current_price + 0.5
        order = bitbank_trade.create_limit_sell_order(symbol, amount, price, params)
        print(order)
        print("Sell Signal")
        print(f"{now} - Selling at {price}")
        sell_price = price
        sell_flg = True
        # sell_cnt =  str(int(sell_cnt) + 1)
    elif current_rsi < 30:
        # RSIが30を下回わり、現金を持っていたら買い
        # price = (math.floor(current_price * 10) / 10) - 0.5
        price = (math.floor(current_price * 10) / 10) - 0.1
        # if sell_flg:
        #     price + 0.3
        # if (current_price - current_price) >= 0.5:
        #     price = current_price - 0.5
        # else:
        #     price = current_price - 1
        if buy_price == price:
            price -= 0.1
        if jpy_balance > amount * price:
            order = bitbank_trade.create_limit_buy_order(symbol, amount, price, params)
            print(order)
            print("Buy Signal")
            print(f"{now} - Buying at {price}")
            buy_price = price
            buy_flg = True
        else:
            orders_merge(open_orders, symbol, params, amount)
    return buy_price, buy_flg, sell_price, sell_flg


def today_timestamp(change_day):
    now = datetime.utcnow()
    if change_day:
        # 現在の日付の0時0分を設定
        next_day = datetime(now.year, now.month, now.day)
        # next_day = datetime(now.year, now.month, now.day) + timedelta(days=1)
        # 次の日の0時0分のUnixタイムスタンプを計算
        unixtime = calendar.timegm(next_day.timetuple())
        since = unixtime * 1000 #0時0分を指定
    else:
        # UTC naiveオブジェクト -> UnixTime
        unixtime = calendar.timegm(now.utctimetuple())
        since = (unixtime - 60 * 15) * 1000 #取得できない時があるので多めに
        # 14分前のUnixTime(ミリ秒)
        # since = (unixtime - 60 * 14) * 1000
    return since


def main():
    env_path = os.environ['ENV_PAHT']
    # 環境変数から初期値を読み込む
    buy_price = float(os.getenv('BUY_PRICE'))
    buy_flg = os.getenv('BUY_FLG')
    sell_price = float(os.getenv('SELL_PRICE'))
    sell_flg = os.getenv('SELL_FLG')
    change_day_flg = False

    # 1分足のデータを取得
    # candles = bitbank_price.fetch_ohlcv("MATIC/JPY", '1m', limit=14)
    # candles = bitbank_price.fetch_ohlcv("MATIC/JPY", '1m', limit=20, since=today_timestamp(change_day_flg))
    candles = bitbank_price.fetch_ohlcv("MATIC/JPY", '5m', limit=20, since=today_timestamp(change_day_flg))
    print("ローソク足:", len(candles))
    if len(candles) < 13:
        change_day_flg = True
        new_candles = bitbank_price.fetch_ohlcv("MATIC/JPY", '5m', limit=20, since=today_timestamp(change_day_flg))
        candles += new_candles

    # データをpandas DataFrameに変換
    df = pd.DataFrame(candles[:14], columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('timestamp', inplace=True)

    def calculate_rsi(data, window=14):
        delta = data['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()

        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    df['RSI'] = calculate_rsi(df)
    print(df['RSI'])

    # 最新のRSI値を取得し、トレードを実行
    current_rsi = df['RSI'].iloc[-1]
    ticker = bitbank_price.fetch_ticker('MATIC/JPY')
    current_price = ticker['last']
    buy_price, buy_flg, sell_price, sell_flg = execute_trade(current_rsi, int(current_price), buy_price, buy_flg, sell_price, sell_flg)
    # print(f"buy_price:{buy_price}")
    # print(f"buy_flg:{buy_flg}")
    # print(f"sell_price:{sell_price}")
    # print(f"sell_flg:{sell_flg}")

    # 環境変数を更新
    update_env_file(env_path, 'BUY_FLG', buy_flg)
    update_env_file(env_path, 'BUY_PRICE', buy_price)
    update_env_file(env_path, 'SELL_FLG', sell_flg)
    update_env_file(env_path, 'SELL_PRICE', sell_price)


if __name__ == "__main__":
    try:
        main()
    finally:
        os.remove(lock_file)

