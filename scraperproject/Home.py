import streamlit as st
from configparser import ConfigParser
from time import sleep
import shopify
from db import dbinit
from models import OurProduct
from settings import get_config, Config
import asyncio
from beanie.operators import NE, Eq
from beanie.odm.enums import SortDirection
from load_to_shopify import update_shopify
# from models import OurProduct

parser = ConfigParser()
CONFIG_FILE = 'config.ini'
shop_url = "bryancommerce.myshopify.com"
api_version = "2023-01"


def check_password():
    """Returns `True` if the user had a correct password."""

    def password_entered():
        """Checks whether a password entered by the user is correct."""
        if (
            st.session_state["username"] in st.secrets["passwords"]
            and st.session_state["password"]
            == st.secrets["passwords"][st.session_state["username"]]
        ):
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # don't store username + password
            del st.session_state["username"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        # First run, show inputs for username + password.
        st.text_input("Username", key="username")
        st.text_input(
            "Password", type="password", key="password"
        )
        st.button("Login", on_click=password_entered)
        return False
    if not st.session_state["password_correct"]:
        # Password not correct, show input + error.
        st.text_input("Username", key="username")
        st.text_input(
            "Password", type="password", key="password"
        )
        st.error("😕 User not known or password incorrect")
        st.button("Login", on_click=password_entered)
        return False
    return True


async def upl_shopify(gpm : int):
    st.write('You have selected:', gpm)
    parser.set('multiplier', 'value', str(gpm))
    with open("config.ini", "w") as f:
        parser.write(f)
        st.info('New value written to disk') 
    progress_text = "Operation in progress. Please wait."

    await dbinit()
    cfg = get_config()
    session = shopify.Session(shop_url, api_version, cfg.shopify.shpat)
    shopify.ShopifyResource.activate_session(session)

    products = await OurProduct.find(NE(OurProduct.optimised, None), NE(OurProduct.optimised.specs, None),).sort((OurProduct.added, SortDirection.DESCENDING)).to_list()
    total = len(products)


    bar = st.progress(0.0, text=progress_text, )
    for i, prod in enumerate(products):
        bar.progress((i+1)/total, text=f'{prod.optimised.title}')

        try:
            await update_shopify(prod, prod.optimised, gpm=gpm, log_func=st)
        except KeyError as e:
            st.critical(prod)
            pass

def btn_callbk(gpm: int):
    st.session_state.disable = True
    asyncio.run(upl_shopify(gpm=gpm))


async def main():

    if check_password():
        
        if 'disable' not in st.session_state:
            st.session_state.disable = False

        st.info('Welcome!')

        st.write("You can adjust price multiplier here for next and future refreshes from DB (Ali) to Shopify. Refreshing the page will get current multiplier value.")

        parser.read(CONFIG_FILE)

        gpm = st.slider("General Price Multiplier", min_value=80, max_value=120, value=int(parser.get('multiplier', 'value')), format="%i%%", step=1, disabled=st.session_state.disable)
        update = st.button('Store new value and update USD prices in Shopify', disabled=st.session_state.disable, on_click=btn_callbk, args=[gpm,])
            

    else:
        st.error('Please authenticate!')



# async def tick(placeholder):
#     tick = 0
#     while True:
#         with placeholder:
#             tick += 1
#             st.write(tick)
#         await asyncio.sleep(1)


# async def main():
#     st.header("Async")
#     placeholder = st.empty()
#     await tick(placeholder)


asyncio.run(main())