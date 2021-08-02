from amazoncaptcha import AmazonCaptcha
from chromedriver_py import binary_path
import coloredlogs
from furl import furl
import json
import logging
from lxml import html
import random
from random_user_agent.params import HardwareType, Popularity, SoftwareType
from random_user_agent.user_agent import UserAgent
import re
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys
import time

SUCCESS = 35
AMAZON_SMILE_BASE_URL = 'https://smile.amazon.com'

def get_random_user_agent(user_agent_rotator, logger):
    user_agent = user_agent_rotator.get_random_user_agent()
    logger.debug(f'using user agent {user_agent}')
    return user_agent

def get_random_proxy(proxies, logger):
    if proxies:
        proxy = random.choice(proxies)
        logger.debug(f'using proxy {proxy}')
        return {'https': f'http://{proxy}'}
    else:
        return None

def calc_time_delta(start_time):
    return int(1000 * (time.time() - start_time))

def check_out(logger, text, s):
    logger.info('trying to check out')

    # get pid and anti_csrf
    pid = re.search(r"pid=(.*?)&amp;", text).group(1)
    logger.debug(f'pid = {pid}')
    anti_csrf = re.search(r"'anti-csrftoken-a2z' value='(.*?)'", text).group(1)
    logger.debug(f'anti_csrf = {anti_csrf}')

    # send place order request
    s.headers.update({'anti-csrftoken-a2z': anti_csrf})
    place_order_url = f'{AMAZON_SMILE_BASE_URL}/checkout/spc/place-order?ref_=chk_spc_placeOrder&clientId=retailwebsite&pipelineType=turbo&pid={pid}'
    start_time = time.time()
    r = s.post(place_order_url)
    logger.debug(f'place order request took {calc_time_delta(start_time)} ms')
    logger.debug(f'place order request returned status code {r.status_code}')
    
    if r.status_code == 500:
        logger.success('checked out')
        exit()
    else:
        logger.warning('could not check out')

def sleep_time_left(next_time):
    time_left = next_time - time.time()
    if time_left > 0:
        time.sleep(time_left)

# create logger
logging.addLevelName(SUCCESS, 'SUCCESS')
logging.Logger.success = lambda self, msg, *args, **kwargs: self._log(SUCCESS, msg, args, **kwargs)
logger = logging.getLogger(__name__)
coloredlogs.install(logging.DEBUG, logger=logger, fmt='%(asctime)s - %(levelname)-7s - %(message)s', level_styles={
    'debug': {'color': 'magenta'},
    'error': {'color': 'red'},
    'success': {
        'bold': True,
        'bright': True,
        'color': 'green',
    },
    'warning': {
        'bright': True,
        'color': 'yellow'
    },
}, field_styles={
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
    browser.get(AMAZON_SMILE_BASE_URL)

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
    next_time_monitor = time.time() + config['delay_monitor']

    logger.info('checking stock')

    try:
        # randomize user agent
        user_agent = get_random_user_agent(user_agent_rotator, logger)

        # randomize proxy
        proxies = get_random_proxy(config['proxies'], logger)

        # send ajax request
        start_time = time.time()
        r = requests.get(f"{AMAZON_SMILE_BASE_URL}/gp/aod/ajax?asin={config['asin']}", cookies={'session-id': ''}, headers={'user-agent': user_agent}, proxies=proxies)
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
                        logger.success('price in range')
                        # get the offering id
                        try:
                            offering_id = offer_div.xpath(".//input[@name='offeringID.1']")[0].value
                            logger.debug(f'offering_id = {offering_id}')
                        except IndexError as e:
                            logger.error(e)
                            continue

                        # build data
                        data = {
                            'offerListing.1': offering_id,
                            'quantity.1': '1',
                        }

                        # create session
                        s = requests.Session()
                        s.headers = {
                            'content-type': 'application/x-www-form-urlencoded',
                            'x-amz-checkout-csrf-token': cookies['session-id'],
                        }
                        for n, v in cookies.items():
                            s.cookies.set(n, v)

                        # calc timeout time
                        timeout_time = time.time() + config['timeout_buy']

                        while True:
                            # calc next time
                            next_time_buy = time.time() + config['delay_buy']

                            logger.info('trying to cart')

                            # randomize user agent
                            s.headers.update({'user-agent': get_random_user_agent(user_agent_rotator, logger)})

                            # randomize proxy
                            s.proxies = get_random_proxy(config['proxies'], logger)

                            # send turbo init request
                            start_time = time.time()
                            r = s.post(f'{AMAZON_SMILE_BASE_URL}/checkout/turbo-initiate?pipelineType=turbo', data)
                            logger.debug(f'turbo init request took {calc_time_delta(start_time)} ms')
                            logger.debug(f'turbo init request returned status code {r.status_code}')

                            if r.status_code == 200:
                                if r.text != ' ':
                                    logger.success('carted')

                                    # check for captcha
                                    captcha_forms = html.fromstring(r.text).xpath('//form[contains(@action, "validateCaptcha")]')
                                    if captcha_forms:
                                        logger.info('got captcha')

                                        # try to solve captcha
                                        captcha_form = captcha_forms[0]
                                        captcha_img_link = captcha_form.xpath('//img[contains(@src, "amazon.com/captcha/")]')[0].attrib['src']
                                        captcha_solution = AmazonCaptcha.fromlink(captcha_img_link).solve()

                                        # check for captcha solution
                                        if captcha_solution:
                                            logger.success('solved captcha')
                                            logger.debug(f'captcha_solution = {captcha_solution}')

                                            # send validate captcha request
                                            captcha_inputs = captcha_form.xpath('.//input')
                                            args = {captcha_input.name: captcha_solution if captcha_input.type == 'text' else captcha_input.value for captcha_input in captcha_inputs}
                                            f = furl(AMAZON_SMILE_BASE_URL)
                                            f.set(path=captcha_form.attrib['action'])
                                            f.add(args=args)
                                            start_time = time.time()
                                            r = s.get(f.url)
                                            logger.debug(f'validate captcha request took {calc_time_delta(start_time)} ms')
                                            logger.debug(f'validate captcha request returned status code {r.status_code}')

                                            check_out(logger, r.text, s)
                                        # no captcha solution
                                        else:
                                            logger.warning('could not solve captcha')
                                    # no captcha
                                    else:
                                        check_out(logger, r.text, s)
                                # no stock
                                else:
                                    logger.warning('could not cart')

                            # check for timeout
                            if timeout_time - time.time() < 0:
                                logger.info('timed out trying to buy')
                                break

                            sleep_time_left(next_time_buy)
    except Exception as e:
        logger.error(e)

    sleep_time_left(next_time_monitor)
