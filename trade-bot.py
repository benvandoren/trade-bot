#!/usr/bin/env python3

import Bittrex
import configparser
from time import sleep

creds = configparser.ConfigParser()
creds.read("api-creds.cfg")
key = creds.get('Bittrex', 'key')
secret = creds.get('Bittrex', 'secret')
bittrex = Bittrex.Bittrex(key, secret)

verbose = 5

config = configparser.ConfigParser()
config.read("trades.cfg")
coins = config.sections() # skips DEFAULT

# initialize dict
openStopSell = {}
openTargetSell = {}
# track when we already have an order on the books
# account for situation where we initiate a high sell but price suddenly drops and we need to execute stop loss sell
for coin in coins:
  openStopSell[coin] = False
  openTargetSell[coin] = False

while True:
  # do forever
  config.read("trades.cfg")
  coins = config.sections()
  
  for coin in coins:
    # TODO catch config errors
    stopTrigger = float(config.get(coin, 'stop-trigger'))
    stopLimit = float(config.get(coin, 'stop-limit'))
    targetTrigger = float(config.get(coin, 'target-trigger'))
    target = float(config.get(coin, 'target'))

    rate = bittrex.get_ticker(coin)
    if verbose > 6:
      print(rate)
    if not rate['success']:
      print("error reading %s coin rate" % (coin))
      continue

    ask = float(rate['result']['Ask'])
    bid = float(rate['result']['Bid'])
    last = float(rate['result']['Last'])

    if verbose > 3:
      print("%s rate: %f" % (coin, ask))

    # check if last is at stop or target; the poll rate may mean we miss some outliers
    # I'm not going to parse get_market_history() or otherwise to get the true high/low 
    # of a time period... it's a feature
    if last <= stopTrigger:
      if not openStopSell[coin]:
        # we're not aware of any orders; check anyway (perhaps a conditional stop was manually placed) and clear it
        bittrex.get_open_orders(coin)
        # sell at stopLimit
        openStopSell[coin] = True
      # else we already set a sell
    elif last >= targetTrigger:
      if not openTargetSell[coin]:
        # sell at target
        openTargetSell[coin] = True
      # else we already set a sell

    # else we wait
  sleep(2)
