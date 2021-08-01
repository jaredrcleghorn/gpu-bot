from chromedriver_py import binary_path
import coloredlogs
import json
import logging
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys

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
