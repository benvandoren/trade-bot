#!/usr/bin/env python3
#
# - supports exchange only
# - currency pairs must be defined as BTC-COIN
# - stop-trigger, stop-limit, target-trigger, target, quantity : must all be defined
# - verbose: 0 errors only, 1 actions only, 2-7 debug
# - you may control quantity, but code will not handle multiple orders; any that exist will be cleared
# - you may modify trades.cfg while script is running
# - dryRun simulates trades using flag
#
# TODO: 
# - Bittrex.py api exceptions
# - more intelligent cancelling (eg. support having a simultaneous buyin and stop loss, 
#   ignore sells that we probably didn't place based on rate/quantity, it's arguable what behavior is desired)
# - refactor 
# - restart if program crashes
# - add time interval to check; larger interval more resilent to outliers, but slower to react
# - display current prices
# - work with more exchanges and specify in coin pair 
#   - have to account for coin pairs no longer being unique
#   - have to make more generic api wrappers (and make high level api library for exchange if it doesn't exist)

import Bittrex
import configparser
from time import sleep
import traceback
import argparse

GREEN = '\033[92m'
RED = '\033[91m'
FAIL = '\033[93m'
ENDC = '\033[0m'

def main(args):
  cfgFile = args.file
  verbose = int(args.verbose)
  dryRun = False if args.dryrun == "false" else True
  print("starting trade bot")
  if dryRun:
    print("dryrun option is set and no real trades will be made")

  try:
    creds = configparser.ConfigParser()
    creds.read("api-creds.cfg")
    key = creds.get('Bittrex', 'key')
    secret = creds.get('Bittrex', 'secret')
    exchange = Bittrex.Bittrex(key, secret)
  except Exception as e:
    print("%serror exception initializing api credentials:%s" % (FAIL, ENDC))
    print("%s%s%s" % (FAIL, e, ENDC))

  try:
    config = configparser.ConfigParser()
    config.read(cfgFile)
    coins = config.sections() # skips DEFAULT
  except Exception as e:
    print("%serror exception reading config file:%s" % (FAIL, ENDC))
    print("%s%s%s" % (FAIL, e, ENDC))
    traceback.print_exc()
    print()

  try:
    # initialize dict
    openStopSell = {}
    idStopSell = {}
    openTargetSell = {}
    idTargetSell = {}
    # track when we already have an order on the books
    print("monitoring following pairs:")
    if not coins:
      print("no coins")
      print("update config file \"%s\" with some coin pairs" % (cfgFile))
    for coin in coins:
      print(coin)
      openStopSell[coin] = False
      idStopSell[coin] = ""
      openTargetSell[coin] = False
      idTargetSell[coin] = ""
      # print(exchange.get_open_orders(coin))
  except Exception as e:
    print("%serror exception initializing coins:%s" % (FAIL, ENDC))
    print("%s%s%s" % (FAIL, e, ENDC))
    traceback.print_exc()
    print()

  while True:
    try:
      # reinstatiate object because otherwise if we remove a 'section' from config file 
      # it will still be cached/stale even when we call read again; the opposite is not true, 
      # calling only read will allow new config items to be sourced in
      config = configparser.ConfigParser() # maybe their is a better solution?
      config.read(cfgFile)
      coins = config.sections()

      for coin in coins:
        # new coin added to cfg
        if coin not in openStopSell:
          openStopSell[coin] = False
          idStopSell[coin] = ""
          openTargetSell[coin] = False
          idTargetSell[coin] = ""

        # TODO catch config errors
        stopTrigger = float(config.get(coin, 'stop-trigger'))
        stopLimit = float(config.get(coin, 'stop-limit'))
        targetTrigger = float(config.get(coin, 'target-trigger'))
        target = float(config.get(coin, 'target'))
        quantity = float(config.get(coin, 'quantity'))

        rate = exchange.get_ticker(coin)
        if verbose > 6:
          print(rate)
        if not rate['success']:
          print("error reading %s coin rate" % (coin))
          continue

        # TODO catch if this is 'NoneType' ??? how does this happen if there is success
        last = float(rate['result']['Last']) # last, ask, bid

        if verbose > 3:
          print("%s rate: %0.8f" % (coin, last))

        # check if last is at stop or target; the poll rate may mean we miss some outliers
        # I'm not going to parse get_market_history() or otherwise to get the true high/low 
        # of a time period... it's a feature
        if last <= stopTrigger:
          placeOrder = True
          # sucks for you, we hit the target trigger, but now the price has dumped and stop loss kicked in; no refunds!
          if openTargetSell[coin]:
            print("%s%s stop-trigger condition %0.8f hit, but we already have a target sell on the books%s" % (RED, coin, stopTrigger, ENDC))
            print("%scancelling target sell %s @ %0.8f%s" % (RED, coin, target, ENDC))
            if not dryRun:
              rtn = exchange.cancel(idTargetSell[coin])
              if not rtn['success']:
                print("error cancel order %s failed; continuing anyway (and we'll attempt to cancel it again before placing sell order)" % (idTargetSell[coin]))
            openTargetSell[coin] = False

          if not openStopSell[coin]:
            if verbose > 0:
              print("%s%s stop-trigger condition %0.8f hit%s" % (RED, coin, stopTrigger, ENDC))
              print("%sselling %s at %0.8f%s" % (RED, coin, stopLimit, ENDC))

            # we're not aware of any orders; check anyway (perhaps a conditional stop was manually placed) and clear it
            orders = exchange.get_open_orders(coin)
            if not orders['success']:
              print("%sapi error fetching current orders for coin %s attempting to place order anyway%s" % (FAIL, coin, ENDC))
              print("%s%s%s" % (FAIL, orders, ENDC))
            else:
              for order in orders['result']:
                print("%sclearing order for %s @ %0.8f%s" % (FAIL, coin, order['price'], ENDC))
                if not dryRun:
                  rtn = exchange.cancel(order['OrderUuid'])
                  if not rtn['success']:
                    print("error cancel order %s failed; attempting to place stop sell anyway" % (order['OrderUuid']))

            if placeOrder:
              if not dryRun:
                rtn = exchange.sell_limit(coin, quantity, stopLimit)
              else:
                rtn = {}
                rtn['success'] = True
                rtn['result'] = "%s_dry_run_stop_sell" % coin
              if not rtn['success']:
                print("%serror placing order failed:%s" % (FAIL, ENDC))
                print("%s%s%s" % (FAIL, rtn, ENDC))
              else:
                if verbose > 0:
                  print("%sorder successfully placed: %s%s" % (RED, rtn["result"], ENDC))
                idStopSell[coin] = rtn["result"]
                openStopSell[coin] = True

        elif last > targetTrigger:
          placeOrder = True
          if not openTargetSell[coin]:
            if verbose > 0:
              print("%s%s target-trigger condition %0.8f hit%s" % (GREEN, coin, targetTrigger, ENDC))
              print("%sselling %s at %0.8f%s" % (GREEN, coin, target, ENDC))

            # we're not aware of any orders; check anyway (perhaps a conditional stop was manually placed) and clear it
            orders = exchange.get_open_orders(coin)
            if not orders['success']:
              print("%sapi error fetching current orders for coin %s attempting to place order anyway%s" % (FAIL, coin, ENDC))
              print("%s%s%s" % (FAIL, orders, ENDC))
            else:
              for order in orders['result']:
                print("%sclearing order for %s @ %0.8f%s" % (FAIL, coin, order['price'], ENDC))
                if not dryRun:
                  rtn = exchange.cancel(order['OrderUuid'])
                  if not rtn['success']:
                    print("error cancel order %s failed; attempting to place stop sell anyway" % (order['OrderUuid']))

            if placeOrder:
              if not dryRun:
                rtn = exchange.sell_limit(coin, quantity, target)
              else:
                rtn = {}
                rtn['success'] = True
                rtn['result'] = "%s_dry_run_target_sell" % coin
              if not rtn['success']:
                print("%serror placing order failed:%s" % (FAIL, ENDC))
                print("%s%s%s" % (FAIL, rtn, ENDC))
              else:
                if verbose > 0:
                  print("%sorder successfully placed: %s%s" % (GREEN, rtn["result"], ENDC))
                idTargetSell[coin] = rtn["result"]
                openTargetSell[coin] = True

        # else we wait
      sleep(2)
    except Exception as e:
      print("%serror exception in main loop:%s" % (FAIL, ENDC))
      print("%s%s%s" % (FAIL, e, ENDC))
      traceback.print_exc()
      print()

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('-f', '--file', help='config file to use', required=False, default="trades.cfg")
    parser.add_argument('-v', '--verbose', help='verbosity level 0 - 7', required=False, default=1)
    parser.add_argument('-d', '--dryrun', help='will not buy/sell/cancel orders, make informational api calls only', required=False, default="false")
    return parser.parse_args()

if __name__ == '__main__':
    main(parse_args())
