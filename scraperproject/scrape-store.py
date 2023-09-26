from secrets import choice
from tenacity import retry, stop_after_attempt, wait_fixed
import asyncio
from playwright_stealth import stealth_async
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
import re

from aiofiles import open
from math import ceil
from datetime import datetime as dt
from loguru import logger
from pathlib import Path
import urllib.parse
from asyncinit import asyncinit
from tqdm import tqdm
from models import AliProduct
from db import dbinit
from settings import get_config, Config, get_filters, Filters

logger.add(f"./logs/{dt.now().timestamp()}.log")

@asyncinit
class Ali:
    store_id: int
    cfg: Config
    browser: Browser
    context: BrowserContext
    page: Page
    total_scraped: int = 0


    async def __init__(self, store_id: int, headless: bool = True):
        self.store_id = store_id
        self.cfg = get_config()
        session = "session.json"
        await dbinit()
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.firefox.launch(headless=headless)
        self.context = await self.browser.new_context(
            # proxy={
            #     "server": "3.230.17.51:31112",
            #     "password": "6WCBj1aKuUpkG4z3",
            #     "username": "commercefy",
            # },
            ignore_https_errors=True,
            record_video_dir="videos/",
            record_video_size=self.cfg.video,
            # record_har_path="./best_stores_and_vevor.har",
            storage_state=session if Path(session).exists() else None,
        )
        self.context.set_default_timeout(self.cfg.timeout)
        await self.context.add_cookies([self.cfg.ali_romanian_usd_cookies])
        self.page = await self.context.new_page()
        # await stealth_async(self.page)
        await self.page.route(
            "**/*",
            lambda route: route.abort()
            if route.request.resource_type in ["stylesheet", "image", "font"]
            else route.continue_(),
        )


        # playwright.locator('punish-component').elements.length 
    async def handle_captcha(self):
        if self.page.locator('punish-component').first:
            # await asyncio.sleep(1)
            logger.warning('captcha!')
            slider = self.page.locator('div.slidetounlock')
            slider_box = await slider.bounding_box()
            # await asyncio.sleep(4)
            logger.debug(slider_box)
            # btn = self.page.locator('span.btn_slide')
            x0 = slider_box['x']
            y0 = slider_box['y'] + 7


            await self.page.mouse.move(x=x0, y=y0, steps=5)

            await self.page.mouse.down()
            for i in range(21):
                await self.page.mouse.move(x0+i*25, y0+i*0.1, steps=2)
                # await asyncio.sleep(0.12)

            await self.page.mouse.up()
            await asyncio.sleep(0.25)
            await self.page.goto(self.page.url+"#")
            await asyncio.sleep(3)
            logger.success('captcha end')
        return True
            # await asyncio.sleep(2)

    async def parse_products(self, pids: list):
        on_page = len(pids)
        self.total_scraped += on_page
        logger.info(f"found {on_page=} products, total={self.total_scraped}")
        for item in tqdm(pids):
            pid = int(item)
            if not await AliProduct.get(pid):
                logger.success(f"found smth new! {pid}")
                new_ali = AliProduct(id=pid)
                _ = await new_ali.save()
            else:
                logger.info(f"already in database {pid=}")

    @retry(reraise=True, stop=stop_after_attempt(2), wait=wait_fixed(4))
    async def open_store_nth_page(
        self,
        store_url: str,
        n: int = 1,
        min_price: int = 0,
        max_price: int = 888,
    ):
        logger.debug(f"opening page {n=}")

        query = urllib.parse.urlencode({
            "origin": "n",
            "sortType": "orders_desc",
        })

        url = f"{store_url}/search/{n}.html?{query}"
        logger.debug(f"{url=}")
        result = await self.page.goto(url)
        assert result.status == 200
        if self.page.url != url:
            logger.warning(f"{result.url=}")

        await self.handle_captcha()
        await self.handle_captcha()
        await self.handle_captcha()

        pattern = r"item/(\d+).html\?pdp_npi=\d.+%24(\d+\.\d+)%21"
        html = await self.page.content()
        matches = set(re.findall(pattern, html))
        pids = [x[0] for x in matches if min_price<= float(x[1]) <= max_price]
        logger.info(f"price matching {len(pids)=} of {len(matches)=}")

        async with open(
            f"./spage/s-{self.store_id}-{n}-{dt.now().timestamp()}.html",
            "w+",
        ) as f:
            await f.write(html)
        total_products = int(re.search(r'"allCount":\'(\d+)\'', html)[1])
        return pids, total_products

    # @retry(reraise=True, stop=stop_after_attempt(4))
    async def scrape_store(self, filters: Filters):
        result = await self.page.goto(f"http://aliexpress.com/store/{self.store_id}")
        assert result.status == 200
        await asyncio.sleep(2)
        await self.handle_captcha()
        await self.handle_captcha()
        await self.handle_captcha()
        store_url = await self.page.locator('link[rel="canonical"]').get_attribute('href')
        logger.info(f"{store_url=}")



        pids, total_products = await self.open_store_nth_page(
            store_url=store_url,
            min_price=filters.min_price,
            max_price=filters.max_price,
        )
        logger.debug(f"{pids=}, {total_products=}")
        page_size = 36
        if total_products:
            logger.debug('.')
            await self.parse_products(pids)
            total_pages = ceil(total_products / page_size)
            logger.info(f"{total_products=} {page_size=} {total_pages=}")
            for n in tqdm(range(2, total_pages + 1)):
                if n >= 5 and self.total_scraped < 3:
                    logger.error("very few matches by price")
                    break
                pids, _ = await self.open_store_nth_page(
                    store_url=store_url,
                    n=n,
                    min_price=filters.min_price,
                    max_price=filters.max_price,
                )
                await self.parse_products(pids)
        else:
            logger.error(f"no results for {self.store_id=}")


async def main(store_id: int):
    filters = get_filters()
    ali = await Ali(store_id=store_id, headless=False)
    await ali.scrape_store(filters)
    await ali.context.storage_state(path='./session.json')
    await ali.browser.close()
    await ali.playwright.stop()


if __name__ == "__main__":
   for store_id in [
        # 2097003,
        # 1114844,
        # 3657097,  
        # 2670054,        
        107430,
        1905224,
        908304,
        605085,
        5483088,
        3181010,
        5080384,
        3157001,
        1852501,
        2823092,
        1396631,
        4594002,
        3482044,
        2847021,
        2629004,
        116732,
        2230155,
        600130,
        1954655,
        2664088,
        610840,
        817474,
        1905163,
        1297540,
        1026126,
        810272,
        3010045,
        5777771,
        5085293,
        2179113,
        103919,
        1986585,
        311331,
        5394047,
        412372,
        5594030,
        1849475,
        4665076,
        5044133,
        4472004,
        5437070,
        4828015,
        4587020,
        1110648,
        628270,
        4178003,
        5131010,
        5891706,
        5597386,
        5881266,
        301635,
        1614012,
        1245004,
        4410143,
        1781058,
        1936564,
        605191,
        1876392,
        1816519,
        4399007,
        4683033,
        4805136,
        715390,
        721071,
        207021,
        1710553,
        1358152,
        198643,
        1455660,
        1405349,
        3240092,
        2231154,
        5068440,
        4844017,
        1473108,
        343737,
        2230079,
        1390488,
        1281164,
        1948940,
        1092020,
        2846085,
        2218051,
        1504763,
        3033013,
        4220011,
        1394297,
        736783,
        1360953,
        1095026,
        2667136,
        1985456,
        3873018,
        50510033,
        3624135,
        2174116,
        1803198,
        2309048,
        234552,
        1963969,
        2223139,
        3201031,
        207828,
        3376005,
        1626381,
        2792173,
        4892036,
        4433130,
        134277,
        5122002,
        4493044,
        3100094,
        5246117,
        732744,
        415596,
        1737030,
        4553041,
        1501890,
        344208,
        4805096,
        2348343,
        3351010,
        2160057,
        5202021,
        5146034,
        5940218,
        3207140,
        601738,
        4513020,
        803060,
        4475139,
        1396009,
        5791057,
        5575088,
        5429187,
        902969,
        5054240,
        2859006,
        1316428,
        2433001,
        206839,
        3194027,
        1919809,
        1774260,
        4431080,
        2820037,
        1535226,
        2667200,
        5037191,
        1420057,
        4998043,
        2965074,
        1543207,
        902861,
        1496322,
        1927090,
        1848566,
        1971362,
        5607049,
        1160570,
        2926073,
        1182691,
        1940618,
        1754978,
        4660154,
        1263469,
        3101008,
        2658104,
        1160888,
        2949141,
        5260219,
        2906274,

        2816005,
        1720100,
        837026,
        1715053,
        4398092,
        4993181,
        4397114,
        4620024,
        1942536,
        616172,
        3624012,
        4664082,
        134518,
        2006033,
        101473,
        1985488,
        409931,
        4441005,
        1166220,
        1192809,
        1190592,
        2661166,
        3091042,
        4681145,
        2286026,
        329366,
        5134034,
        2133138,
        1767224,
        723781,
        1779121,
        4233052,
        2061134,
        1814259,
        2659156,
        536080,
        1921742,
        1327086,
        830320,
        1081378,
        3185017,
        510486,
        5066190,
        2349025,
        324002,
        2132090,
        2789106,
        831584,
        919909,
        3616100,
        3204072,
        5589036,
        3375033,
        4417150,
        3172006,
        3737015,
        1924412,
        1017585,
        2667131,
        4987065,
        838107,
        1854241,
        2344236,
        500715,
        4710105,
        5082386,
        2811108,
        3583004,
        1841016,
        1801824,
        1936258,
        1362086,
        1891209,
        1805507,
        3095007,
        300086,
        910293,
        1953446,
        3081060,
        1513187,
        1805104,
        4187019,
        4257014,
        1182006,
        233632,
        317945,
        528552,
        704776,
        1494610,
        1937952,
        426795,
        1122077,
        403498,
        3042038,
        2934031,
        2539007,
        3146011,
        705688,
        1445055,
        311789,
        200155,
        1722416,
        1314191,
        1229333,
        233135,
        1946246,
        4477006,
        2338005,
        1473227,
        3873085,
        1489256,
        1013215,
        420740,
        5055215,
        5580082,
        4920069,
        911256097,
        516520,
        836958,
        1541572,
        1969584,
        5101109,
        4056069,
        4991183,
        3247038,
        5628316,
        1988461,
        5063216,
        2534028,
        5422073,
        2183003,
        928740,
        3900024,
        1596075,
        2948169,
        1895392,
        3508044,
        3612015,
        5129020,
        4403001,
        3662033,
        2923039,
        324966,
        1422074,
        1904827,
        3215018,
        2958183,
        4922106,
        636721,
        3518093,
        2569001,
        2385039,
        639841,
        812908,
        218136,
        2347030,
        1958918,
        1479025,
        4086004,
        129298,
        3223008,
        2165063,
        5000213,
        2829074,
        2026087,
        1971349,
        2131051,
        918303,
        2475030,
        5099040,
        5748186,
        1771169,
        1709978,
        3109002,
        1314579,
        822557,
        5440128,
        1820339,
        1666612,
        535744,
        1160268,
        3462006,
        1835326,
        728949,
        2786181,
        5041024,
        301731,
        2831034,
        804723,        
    ]:
        logger.info(f"{store_id=}")
        asyncio.run(main(store_id))
