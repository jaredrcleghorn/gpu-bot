from chromedriver_py import binary_path
import coloredlogs
import json
import logging
from lxml import html
from random_user_agent.params import HardwareType, Popularity, SoftwareType
from random_user_agent.user_agent import UserAgent
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys
import time

# create logger
logger = logging.getLogger(__name__)
coloredlogs.install(logging.DEBUG, logger=logger, fmt='%(asctime)s - %(levelname)s - %(message)s', field_styles={
    'asctime': {'color': 'blue'},
    'levelname': {'color': 'cyan'},
})

# read config file
with open('config.json') as f:
    config = json.loads(f.read())

logger.info('signing in')

# create browser
options = Options()
options.add_argument('--headless')
browser = webdriver.Chrome(binary_path, options=options)

try:
    # go to amazon
    browser.get('https://smile.amazon.com')

    # click sign in
    browser.find_element_by_xpath('//*[@id="ge-hello"]/div/span/a').click()

    # enter email
    email_input = browser.find_element_by_id('ap_email')
    browser.execute_script(f"arguments[0].value = '{config['email']}'", email_input)
    email_input.send_keys(Keys.RETURN)

    # enter password and check keep me signed in
    password_input = browser.find_element_by_id('ap_password')
    browser.execute_script(f"arguments[0].value = '{config['password']}'", password_input)
    browser.find_element_by_name('rememberMe').click()
    password_input.send_keys(Keys.RETURN)

    # get cookies
    cookies = {n: browser.get_cookie(n)['value'] for n in ['at-main', 'session-id', 'ubid-main']}
    logger.debug(f'cookies = {cookies}')
except:
    logger.error('could not sign in')
finally:
    # destroy browser
    browser.quit()

# create user agent rotator
user_agent_rotator = UserAgent(hardware_types=[HardwareType.COMPUTER.value], software_types=[SoftwareType.WEB_BROWSER.value], popularity=[Popularity.POPULAR.value])

while True:
    # calc next time
    next_time = time.time() + config['delay']

    # randomize user agent
    user_agent = user_agent_rotator.get_random_user_agent()
    logger.debug(f'using user agent {user_agent}')

    logger.info('checking stock')

    # send ajax request
    start_time = time.time()
    r = requests.get(f"https://smile.amazon.com/gp/aod/ajax?asin={config['asin']}", cookies={'session-id': ''}, headers={'user-agent': user_agent})
    logger.debug(f'ajax request took {int(1000 * (time.time() - start_time))} ms')
    logger.debug(f'ajax request returned status code {r.status_code}')

    if r.status_code == 200:
        offer_divs = html.fromstring(r.text).xpath("//div[@id='aod-sticky-pinned-offer'] | //div[@id='aod-offer']")

        for offer_div in offer_divs:
            price_spans = offer_div.xpath(".//span[@class='a-price-whole']")

            if price_spans:
                price = int(price_spans[0].text.replace(',', ''))
                logger.info(f'offer for ${price}')

                # check price
                if config['min_price'] <= price <= config['max_price']:
                    offering_id = offer_div.xpath(".//input[@name='offeringID.1']")[0].value
                    logger.debug(f'offering_id = {offering_id}')

    # sleep time left
    time_left = next_time - time.time()
    if time_left > 0:
        time.sleep(time_left)
