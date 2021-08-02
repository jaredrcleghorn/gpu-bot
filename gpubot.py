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
import threading
import time

SUCCESS = 35
MAIN_LOG_NAME = 'MAIN'
AMAZON_SMILE_BASE_URL = 'https://smile.amazon.com'

def calc_time_delta(start_time):
    return int(1000 * (time.time() - start_time))

def sleep_time_left(next_time):
    time_left = next_time - time.time()
    if time_left > 0:
        time.sleep(time_left)

class ItemThread(threading.Thread):
    def __init__(self, item, logger, delay_monitor, delay_buy, timeout_buy, user_agent_rotator, proxies, cookies):
        super().__init__()

        self.item = item
        self.logger = logging.LoggerAdapter(logger, {'logname': item['name']})
        self.delay_monitor = delay_monitor
        self.delay_buy = delay_buy
        self.timeout_buy = timeout_buy
        self.user_agent_rotator = user_agent_rotator
        self.proxies = proxies
        self.cookies = cookies

    def get_random_user_agent(self):
        user_agent = self.user_agent_rotator.get_random_user_agent()
        self.logger.debug(f'using user agent {user_agent}')
        return user_agent

    def get_random_proxy(self):
        if self.proxies:
            proxy = random.choice(self.proxies)
            self.logger.debug(f'using proxy {proxy}')
            return {'https': f'http://{proxy}'}
        else:
            return None

    def check_out(self, text, s):
        self.logger.info('trying to check out')

        # get pid and anti_csrf
        pid = re.search(r"pid=(.*?)&amp;", text).group(1)
        self.logger.debug(f'pid = {pid}')
        anti_csrf = re.search(r"'anti-csrftoken-a2z' value='(.*?)'", text).group(1)
        self.logger.debug(f'anti_csrf = {anti_csrf}')

        # send place order request
        s.headers.update({'anti-csrftoken-a2z': anti_csrf})
        place_order_url = f'{AMAZON_SMILE_BASE_URL}/checkout/spc/place-order?ref_=chk_spc_placeOrder&clientId=retailwebsite&pipelineType=turbo&pid={pid}'
        start_time = time.time()
        r = s.post(place_order_url)
        self.logger.debug(f'place order request took {calc_time_delta(start_time)} ms')
        self.logger.debug(f'place order request returned status code {r.status_code}')
        
        if r.status_code == 500:
            self.logger.success('checked out')
            exit() # NOTE: not sure what this does in thread
        else:
            self.logger.warning('could not check out')

    def run(self):
        while True:
            # calc next time
            next_time_monitor = time.time() + self.delay_monitor

            self.logger.info('checking stock')

            try:
                # randomize user agent
                user_agent = self.get_random_user_agent()

                # randomize proxy
                proxies = self.get_random_proxy()

                # send ajax request
                start_time = time.time()
                r = requests.get(f"{AMAZON_SMILE_BASE_URL}/gp/aod/ajax?asin={self.item['asin']}", cookies={'session-id': ''}, headers={'user-agent': user_agent}, proxies=proxies)
                self.logger.debug(f'ajax request took {int(1000 * (time.time() - start_time))} ms')
                self.logger.debug(f'ajax request returned status code {r.status_code}')

                if r.status_code == 200:
                    offer_divs = html.fromstring(r.text).xpath("//div[@id='aod-sticky-pinned-offer'] | //div[@id='aod-offer']")

                    for offer_div in offer_divs:
                        price_spans = offer_div.xpath(".//span[@class='a-price-whole']")

                        if price_spans:
                            price = int(price_spans[0].text.replace(',', ''))
                            self.logger.info(f'offer for ${price}')

                            # check price
                            if self.item['min_price'] <= price <= self.item['max_price']:
                                self.logger.success('price in range')

                                # get the offering id
                                offering_id = offer_div.xpath(".//input[@name='offeringID.1']")[0].value
                                self.logger.debug(f'offering_id = {offering_id}')

                                # build data
                                data = {
                                    'offerListing.1': offering_id,
                                    'quantity.1': '1',
                                }

                                # create session
                                s = requests.Session()
                                s.headers = {
                                    'content-type': 'application/x-www-form-urlencoded',
                                    'x-amz-checkout-csrf-token': self.cookies['session-id'],
                                }
                                for n, v in self.cookies.items():
                                    s.cookies.set(n, v)

                                # calc timeout time
                                timeout_time = time.time() + self.timeout_buy

                                while True:
                                    # calc next time
                                    next_time_buy = time.time() + self.delay_buy

                                    self.logger.info('trying to cart')

                                    # randomize user agent
                                    s.headers.update({'user-agent': get_random_user_agent()})

                                    # randomize proxy
                                    s.proxies = get_random_proxy()

                                    # send turbo init request
                                    start_time = time.time()
                                    r = s.post(f'{AMAZON_SMILE_BASE_URL}/checkout/turbo-initiate?pipelineType=turbo', data)
                                    self.logger.debug(f'turbo init request took {calc_time_delta(start_time)} ms')
                                    self.logger.debug(f'turbo init request returned status code {r.status_code}')

                                    if r.status_code == 200:
                                        if r.text != ' ':
                                            self.logger.success('carted')

                                            # check for captcha
                                            captcha_forms = html.fromstring(r.text).xpath('//form[contains(@action, "validateCaptcha")]')
                                            if captcha_forms:
                                                self.logger.info('got captcha')

                                                # try to solve captcha
                                                captcha_form = captcha_forms[0]
                                                captcha_img_link = captcha_form.xpath('//img[contains(@src, "amazon.com/captcha/")]')[0].attrib['src']
                                                captcha_solution = AmazonCaptcha.fromlink(captcha_img_link).solve()

                                                # check for captcha solution
                                                if captcha_solution:
                                                    self.logger.success('solved captcha')
                                                    self.logger.debug(f'captcha_solution = {captcha_solution}')

                                                    # send validate captcha request
                                                    captcha_inputs = captcha_form.xpath('.//input')
                                                    args = {captcha_input.name: captcha_solution if captcha_input.type == 'text' else captcha_input.value for captcha_input in captcha_inputs}
                                                    f = furl(AMAZON_SMILE_BASE_URL)
                                                    f.set(path=captcha_form.attrib['action'])
                                                    f.add(args=args)
                                                    start_time = time.time()
                                                    r = s.get(f.url)
                                                    self.logger.debug(f'validate captcha request took {calc_time_delta(start_time)} ms')
                                                    self.logger.debug(f'validate captcha request returned status code {r.status_code}')

                                                    self.check_out(r.text, s)
                                                # no captcha solution
                                                else:
                                                    self.logger.warning('could not solve captcha')
                                            # no captcha
                                            else:
                                                self.check_out(r.text, s)
                                        # no stock
                                        else:
                                            self.logger.warning('could not cart')

                                    # check for timeout
                                    if timeout_time - time.time() < 0:
                                        self.logger.info('timed out trying to buy')
                                        break

                                    sleep_time_left(next_time_buy)
            except Exception as e:
                self.logger.error(e)

            sleep_time_left(next_time_monitor)

# read config file
with open('config.json') as f:
    config = json.loads(f.read())

# create logger
logging.addLevelName(SUCCESS, 'SUCCESS')
logging.Logger.success = lambda self, msg, *args, **kwargs: self._log(SUCCESS, msg, args, **kwargs)
logger = logging.getLogger(__name__)
max_log_name_len = len(MAIN_LOG_NAME)
for item in config['items']:
    name_len = len(item['name'])
    if name_len > max_log_name_len:
        max_log_name_len = name_len
coloredlogs.install(logging.DEBUG, logger=logger, fmt=f'%(asctime)s - %(levelname)-7s - %(logname)-{max_log_name_len}s - %(message)s', level_styles={
    'debug': {
        'bright': True,
        'color': 'black'
    },
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
    'logname': {'color': 'magenta'},
})
adapter = logging.LoggerAdapter(logger, {'logname': MAIN_LOG_NAME})

adapter.info('signing in')

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
    adapter.debug(f'cookies = {cookies}')
except:
    adapter.error('could not sign in')
finally:
    # destroy browser
    browser.quit()

# create user agent rotator
user_agent_rotator = UserAgent(hardware_types=[HardwareType.COMPUTER.value], software_types=[SoftwareType.WEB_BROWSER.value], popularity=[Popularity.POPULAR.value])

# start item threads
for item in config['items']:
    item_thread = ItemThread(item, logger, config['delay_monitor'], config['delay_buy'], config['timeout_buy'], user_agent_rotator, config['proxies'], cookies)
    item_thread.start()
