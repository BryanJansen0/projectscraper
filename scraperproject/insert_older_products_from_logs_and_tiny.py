from tenacity import retry, stop_after_attempt
import asyncio
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
import json
import re
from glob import glob
from random import shuffle
from aiofiles import open
from math import ceil
from datetime import datetime as dt
from loguru import logger
import urllib.parse
from asyncinit import asyncinit
from tqdm import tqdm
from models import AliProduct, DetailedListing
from db import dbinit
from settings import get_config, Config, get_filters, Filters
from beanie.operators import Eq
from tinydb import TinyDB



# category-list => evaluation.starRating:4.7
# category-list => trade.tradeDesc:"47 sold"


# detailed.imageModule.imagePathList
# detailed.skuModule.skuPriceList[].skuVal.availQuantity:26
# detailed.storeModule.followingNumber
#                     .positiveRate:"96.4%"

# detailed.titleModule.subject / category-list => title.seoTitle
# detailed.pageModule.description
# detailed.pageModule.keywords
# storeModule.topRatedSeller == True


# detailed.data.shippingModule.generalFreightInfo.originalLayoutResultList []
# detailed hideShipFrom:true
# detailed.additionLayout → componentId 929 1189
# detailed.bizData.deliveryProviderName
# detailed.bizData.shipFrom
# detailed.bizData.deliveryDayMax 7
# detailed.deliveryOptionPanelDisplayList [str] → componentId 3042 - 7day delivery




async def main():
    await dbinit()
    ids = [x.id for x in await AliProduct.find_all().to_list()]
    items = glob('./prods/p*.json')
    items = [int(i.split('-')[1]) for i in items]
    tiny = TinyDB("./db2.json")
    prods = tiny.table("products")
    prods = [x.doc_id for x in prods.all()]
    items.extend(prods)

    for item in tqdm(items):
        if item not in ids:
            logger.success(f"found smth new! {item}")
            await AliProduct(id=item).save()


if __name__ == "__main__":
    asyncio.run(main())
