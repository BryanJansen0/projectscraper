from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient
from models import AliProduct, OurProduct, Ean, AliProductIdOnly, OurProductIdOnly


async def dbinit():
    # Create Motor client
    client = AsyncIOMotorClient("mongodb+srv://scraper:KwZxiR4MSUEzxLXk@commercefy.wilck.mongodb.net/?retryWrites=true&w=majority")
    # Initialize beanie with the Product document class and a database
    await init_beanie(
        database=client.commercefy, document_models=[AliProduct, AliProductIdOnly, OurProduct, Ean, OurProductIdOnly]
    )
