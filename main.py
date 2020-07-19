import gevent.monkey
gevent.monkey.patch_all()
import json
import random
import discord
import requests
import cloudscraper
from pathlib import Path
from asyncio import sleep
from steam.client import SteamClient
from steam.steamid import SteamID
from csgo.client import CSGOClient
from csgo.proto_enums import GCConnectionStatus
from selenium import webdriver
from selenium.webdriver import ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions
from selenium.common.exceptions import NoSuchElementException
from cloudscraper import CloudScraper
from bs4 import BeautifulSoup

client = discord.Client()
steam = SteamClient()
cs = CSGOClient(steam)

RANK_STRINGS = ['S1', 'S2', 'S3', 'S4', 'SE', 'SEM', 'GN1', 'GN2', 'GN3', 'GN4', 'MG1', 'MG2', 'MGE', 'DMG', 'LE', 'LEM', 'SMFC', 'Global']
#matt, hugo, jack, george, nick, thett, michael, face
PLAYER_IDS = {136875501544407041: 76561198091230520, 200924489582772235: 76561198140621134, 234383468417646594: 76561198118173367,
            409385026598469643: 76561198251909246, 667165895201914881: 76561198118694624, 200929868802686976: 76561198093943295,
            191284442696908800: 76561198102369818, 136875471328641024: 76561198085285285}
PROXIES = []
DISCORD_TOKEN = 'NzI1NjU5MDc1MzMzMDYyNjY3.XwUeAw.wExIe5URkpmP5zjTio8otOtHUv4'
ANTICAPTCHA_KEY = 'de94b455e7c758495f15a15e11c334f2'
CLOUDSCRAPER_SESSION = None

def get_steam_id(discord_id):
    if discord_id in PLAYER_IDS: return PLAYER_IDS[discord_id]
    return -1

def check_proxy_working(proxy):
    try:
        requests.get('http://google.com',
            proxies = proxy,
            timeout = 0.5
        )
        return True
    except:
        return False

def get_proxy():
    for _ in range(len(PROXIES)):
        proxy_number = random.randint(0, len(PROXIES))
        proxy = PROXIES[proxy_number]
        if check_proxy_working(proxy):
            return proxy
    return {}


def get_ranks_selenium(steam_id):
    user_agent = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/83.0.4103.116 Safari/537.36'
    options = webdriver.ChromeOptions()
    options.add_argument('headless')
    options.add_argument(f'user-agent={user_agent}')
    options.add_argument("window-size=1920x1080")
    driver = webdriver.Chrome(options=options)
    try:
        driver.get('https://csgostats.gg/player/{}#/live'.format(steam_id))
        WebDriverWait(driver, 10).until(
            expected_conditions.presence_of_element_located((By.ID, 'player-live'))
        )
    except:
        driver.quit()
        return 'Cannot load csgostats'
    try:
        element = driver.find_element_by_id('player-live')
        WebDriverWait(driver, 10).until(lambda wd: 'content-tab current-tab' in element.get_attribute('class'))
        WebDriverWait(driver, 10).until(lambda wd: len(element.find_elements_by_tag_name('style')) != 0)
    except:
        driver.quit()
        return 'Cannot load live data from csgostats, being blocked'
    if 'This player is current not in a live match!' in element.get_attribute('innerHTML'):
        driver.quit()
        return 'Player not in game!'
    try:
        element = driver.find_element_by_class_name('scoreboard')
    except NoSuchElementException:
        driver.quit()
        return 'Cannot parse csgostats live data'
    ranks = {}
    rows = element.find_elements_by_tag_name('tr')
    for row in rows:
        columns = row.find_elements_by_tag_name('td')
        if len(columns) > 6:
            name = columns[0].find_element_by_tag_name('span').text
            try:
                rank_url = columns[2].find_element_by_tag_name('img').get_attribute('src')
                rank = RANK_STRINGS[int(Path(rank_url).stem)-1]
            except:
                rank = '???'
            ranks[name] = rank
    ranks = '\n'.join(['%s: %s' % (key, value) for (key, value) in ranks.items()])
    driver.quit()
    return ranks

def get_ranks_cloudscraper(steam_id):
    scraper = CloudScraper(
        recaptcha={
            'provider': 'anticaptcha',
            'api_key': ANTICAPTCHA_KEY
        }
    )
    try:
        scraper.get('https://csgostats.gg/player/{}'.format(steam_id))
        live_json = scraper.get('https://csgostats.gg/player/{}/live'.format(steam_id)).text
    except Exception as e:
        print(e)
        return 'csgostats has blocked this request, try again in a moment'
    if 'This player is current not in a live match' in live_json:
        return 'Player not in game!'
    try:
        live_html = json.loads(live_json)['content']
        soup = BeautifulSoup(live_html, 'html.parser')
        tbody_list = soup.find_all('tbody')
        ranks = {}
        for j in range(0, 3, 2):
            tr_data = tbody_list[j].find_all('tr')
            for i in range(5):
                td_data = tr_data[i].find_all('td')
                try:
                    name = td_data[0].a.span.string
                except:
                    name = '???'
                try:
                    rank = RANK_STRINGS[int(Path(td_data[2].img['src']).stem)-1]
                except:
                    rank = '???'
                ranks[name] = rank
        ranks = '\n'.join(['%s: %s' % (key, value) for (key, value) in ranks.items()])
    except:
        return 'Cannot parse csgostats live data'
    return ranks

async def get_player_data_cloudscraper(steam_id):
    """Uses the cloudscraper library to get player information from csgostats.gg

    Args:
        steam_id (string): Steam64ID of user
    """
    scraper = cloudscraper.create_scraper(
        sess=CLOUDSCRAPER_SESSION, #should be passed by reference and therefore up-to-date
        recaptcha={
        'provider': 'anticaptcha',
        'api_key': ANTICAPTCHA_KEY
    }
    )
    #TODO: Try and make try/excepts cleaner
    max_attempts = 5
    while max_attempts > 0:
        try:
            page = scraper.get('https://www.csgostats.gg/player/{}'.format(steam_id)).text
            break
        except Exception as e:
            print(e)
            max_attempts-=1
            await sleep(random.randint(1, 10)/10)
            if max_attempts == 0: return 'Can\'t load csgostats page'
    try:
        soup = BeautifulSoup(page, 'html.parser')
    except:
        return 'Can\'t parse csgostats page'
    try:
        name = soup.find('div', id='player-name').string
    except:
        name = 'Cannot load name of {}'.format(steam_id)
    try:
        summary = soup.find('meta', property='og:description')['content']
    except:
        summary = '???'
    try:
        rank_element = None
        rank_element = soup.find('img', width='92')
        try:
            rank = rank_element['data-cfsrc']
        except:
            rank = rank_element['src']
        rank = RANK_STRINGS[int(Path(rank).stem)-1]
    except Exception as e:
        print(e)
        rank = '???'
    return '{}\n  {}\n  {}'.format(name, rank, summary)

async def get_live_match_info(steam_id, update_message):
    """Uses csgo game coordinator to get details of live game

    Args:
        steam_id (string): Steam64ID of user
    """
    try:
        if steam.logged_on is not True:
            steam_relogin()
        elif cs.connection_status is not GCConnectionStatus.HAVE_SESSION:
            cs.launch()
        cs.request_live_game_for_user(SteamID(steam_id).id)
        response, = cs.wait_event('live_game_for_user', timeout=2) #blocking call, should make async
    except TypeError:
        await update_message.edit(content='Player not in game!')
        return
    except:
        await update_message.edit(content='Cannot connect to csgo game coordinator, try again later')
        return
    try:
        players = [str(SteamID(i).as_64) for i in response.matches[0].roundstats_legacy.reservation.account_ids]
    except:
        await update_message.edit(content='Player not in game')
        return
    players_info = list()
    for player in players:
        players_info.append(await get_player_data_cloudscraper(player))
        await update_message.edit(content='\n'.join(players_info))

# async def get_ranks(steam_id, update_message):
#     # status = get_ranks_cloudscraper(steam_id)
#     # if status == 'csgostats has blocked this request, try again in a moment':
#     #     print('Had to resort to fallback')
#     #     await update_message.edit(content='csgostats has blocked this request, dropping to fallback...')
#     #     status = get_ranks_selenium(steam_id)
#     status = get_live_match(steam_id)
#     await update_message.edit(content=status)

async def get_live_player(update_message):
    """Gets a random player currently in a live match

    Args:
        update_message ([type]): Message to update info via.
    """
    try:
        if steam.logged_on is not True:
            steam_relogin()
        elif cs.connection_status is not GCConnectionStatus.HAVE_SESSION:
            cs.launch()
        cs.request_current_live_games()
        response, = cs.wait_event('current_live_games', timeout=2) #blocking call, should make async
    except TypeError:
        await update_message.edit(content='No live games found!')
        return
    except:
        await update_message.edit(content='Cannot connect to csgo game coordinator, try again later')
        return
    player = response.matches[0].roundstats_legacy.reservation.account_ids[0] #TODO: make random
    await update_message.edit(content=SteamID(player).as_64)

@steam.on('logged_on')
@steam.on('reconnect')
def start_csgo():
    if cs.connection_status is not GCConnectionStatus.HAVE_SESSION:
        cs.launch()

@steam.on('disconnected')
def steam_relogin(): #this may not be the right way to handle a steam disconnect
    steam.relogin() #should probably implement steam.relogin_available

@client.event
async def on_ready():
    print('We have logged in as {0.user}'.format(client))

@client.event
async def on_message(message):
    if message.author == client.user:
        return
    try:
        if message.content.startswith('!randomliveplayer'):
            print('Random player request from {}'.format(message.author.name))
            sent_message = await message.channel.send('Loading...')
            await get_live_player(sent_message)
        if message.content.startswith('!checkranksof'):
            print('Request from {}'.format(message.author.name))
            steam_id = message.content.split(' ')[1]
            sent_message = await message.channel.send('Loading...')
            await get_live_match_info(steam_id, sent_message)
        elif message.content.startswith('!checkranks') or message.content.startswith('!checkgame'):
            print('Request from {}'.format(message.author.name))
            steam_id = get_steam_id(message.author.id)
            if steam_id == -1:
                await message.channel.send('Can\'t find your game, no steam id known.')
                return
            sent_message = await message.channel.send('Loading...')
            await get_live_match_info(steam_id, sent_message)
    except Exception as exception:
        print(exception)

if __name__ == '__main__':
    steam.login()
    client.run(DISCORD_TOKEN)