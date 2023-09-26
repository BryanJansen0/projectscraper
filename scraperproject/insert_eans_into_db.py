import pandas as pd
from models import Ean
from db import dbinit
import asyncio









async def main():
    await dbinit()

    existing = await Ean.find_all().to_list()
    existing = [x.id for x in existing]

    # eans = pd.read_excel('product_scraper/First 1000 ean codes.xlsx').T.values[0].tolist()
    eans = pd.read_csv('8563.csv', header=None, names=["ean"]).ean.values.tolist()
    eans = [Ean(id=ean) for ean in eans if ean not in existing]

    await Ean.insert_many(eans)


if __name__ == "__main__":
    asyncio.run(main())
