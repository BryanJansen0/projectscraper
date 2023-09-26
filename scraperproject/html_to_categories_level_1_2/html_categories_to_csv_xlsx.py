from parsel import Selector
from requests import get
from pathlib import Path
from pydantic import BaseModel, HttpUrl
import pandas as pd


class CatPath(BaseModel):
    level1_name: str
    level1_id: int
    level1_link: HttpUrl
    level2_name: str
    level2_id: int
    level2_link: HttpUrl


# https://www.aliexpress.com/all-wholesale-products.html
html = Path("categories.html").read_text()

sel = Selector(html)
records = []
for majorcat in sel.css("div.cg-main div.item"):
    level1_name = majorcat.css("h3 a").xpath("text()").get()
    level1_link = "https:" + majorcat.css("h3 a").xpath("@href").get()
    _, level1_id, _ = level1_link.rsplit("/", maxsplit=2)

    for subcat1 in majorcat.css("ul li a"):
        level2_name = subcat1.xpath("text()").get()
        level2_link = "https:" + subcat1.xpath("@href").get()
        _, level2_id, _ = level2_link.rsplit("/", maxsplit=2)

        catpath = CatPath(
            level1_name=level1_name,
            level1_id=level1_id,
            level1_link=level1_link,
            level2_name=level2_name,
            level2_id=level2_id,
            level2_link=level2_link,
        )
        records.append(catpath.dict())

pd.DataFrame(records).to_csv("categories_level_1_and_2.csv")
pd.DataFrame(records).to_excel("categories_level_1_and_2.xlsx")
