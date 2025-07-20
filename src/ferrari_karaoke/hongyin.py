import nodriver as uc
import atexit
import httpx
import json
import pandas as pd
import time
import random
import ipdb
import tempfile
import shutil
from pathlib import Path
import logging

BASE_URL = "https://song.corp.com.tw"
COMPANY = "弘音"
EXAMPLE_ENTRY = {
    'seq': 1313001341,
    'id': 1457393,
    'songDetailID': 3308719,
    'name': '戲台',
    'code': '99344',
    'subname': '',
    'singer': '蔡秋鳳',
    'lang': '台',
    'company': '弘音',
    'songDate': '114-05',
}
#EXAMPLE_ENTRY = {
#    'seq': 2908,
#    'id': 170479,
#    'code': '88433',
#    'name': '可憐的小姑娘',
#    'singer': '郭金發',
#    'lang': '台',
#    'sex': '男',
#    'company': '弘音',
#    'songDate': '114-03',
#    'subname': '',
#    'songDetailID': '12032',
#    'counter': 7497,
#    'dateSorter': 11403,
#    'len': 6,
#    'artistIMG': 'https://i.kfs.io/artist/global/21452,0v1/fit/300x300.jpg',
#}
USED_COLUMNS = ["code", "name", "singer", "lang"]
LANGS = ("台", "國", "日", "客", "粵", "英", "山", "兒")

PROJECT_ROOT_DIR = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT_DIR/"data"
ASSETS_DIR = PROJECT_ROOT_DIR/"assets"

SLEEP_MIN_SEC = 2
SLEEP_MAX_SEC = 5
NUM_GETS_BEFORE_SLEEP_AGAIN = random.randint(10, 20)

logger = logging.getLogger("hongyin")
#logger = logging.getLogger(__name__)
#print(f'{logger.name = }')


def setup_logging():
    config_file = Path(__file__).parent/"config/logging/queued-stdout-stderr-file.json"
    with open(config_file) as f:
        config = json.load(f)

    #ipdb.set_trace()
    logs_dir = Path(config["handlers"]["file_json"]["filename"]).parent
    logs_dir.mkdir(parents=True, exist_ok=True)
    logging.config.dictConfig(config)
    queue_handler = logging.getHandlerByName("queue_handler")
    if queue_handler is not None:
        queue_handler.listener.start()
        atexit.register(queue_handler.listener.stop)


async def crawl_songs(keep_csv: bool = True):
    """
    Works by simulate infinite-scrolling triggered request
    """
    if keep_csv:
        DATA_DIR.mkdir(parents=True, exist_ok=True)

    big_df = pd.DataFrame({
        col: pd.Series(dtype="str") for col in USED_COLUMNS
    })

    browser = await uc.start(headless=True)
    cookies_dict = {c.name: c.value for c in await browser.cookies.get_all()}
    client = httpx.Client(cookies=cookies_dict)

    for lang in LANGS:
        logger.debug(f'{lang = }')
        min_id = 0
        num_gets = 0
        df = pd.DataFrame({
            k: pd.Series(dtype="str")
            if isinstance(v, str) else
            pd.Series(dtype="int64")
            for k, v in EXAMPLE_ENTRY.items()
        })
        while True:
            url = (f'{BASE_URL}/api/song.aspx?company={COMPANY}&cusType=new'
                   f'&minId={min_id}&oid=&lang={lang}&board=&keyword='
                   f'&singer=&sex=&Len=&songDate=null')
            #logger.warning(f'{url = }')
            response = client.get(url)
            if response.status_code != 200:
                #print(f'{response.status_code = }')
                msg = (f'{url = }\n'
                       f'{response.status_code = }')
                logger.warn(msg)
                #ipdb.set_trace()
            num_gets += 1
            L = json.loads(response.content)
            if len(L) == 0:
                break
            for new_row in L:
                df.loc[len(df)] = new_row
            min_id = L[-1]["seq"]
            if num_gets > NUM_GETS_BEFORE_SLEEP_AGAIN:
                sleep_sec = random.randint(SLEEP_MIN_SEC, SLEEP_MAX_SEC)
                #NUM_GETS_BEFORE_SLEEP = random.randint(10, 20)
                time.sleep(sleep_sec)
                num_gets = 0

        print(f'{df.dtypes = }')
        #ipdb.set_trace()
        if keep_csv:
            df.to_csv(DATA_DIR/f'{lang}.csv', index=False)

        sub_df = df.loc[:, USED_COLUMNS]
        big_df = pd.concat(
            [big_df, sub_df],
            ignore_index=True,
        )

    return big_df


def save_songs_in_jsonl(songs_df: None | pd.DataFrame = None):
    #ipdb.set_trace()
    if songs_df is None or songs_df.empty:
        songs_df = pd.DataFrame({
            col: pd.Series(dtype="str") for col in USED_COLUMNS
        })
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        csv_paths = [DATA_DIR/f'{lang}.csv' for lang in LANGS]
        if all(p.exists() for p in csv_paths):
            #print(f'{csv_paths = }')
            #ipdb.set_trace()
            for p in csv_paths:
                df = pd.read_csv(
                    p,
                    usecols=USED_COLUMNS,
                )
                songs_df = pd.concat(
                    [songs_df, df],
                    ignore_index=True,
                )
        else:
            # TODO: Logging
            msg = []
            for lang in LANGS:
                p = DATA_DIR/f'{lang}.csv'
                if not p.exists():
                    msg.append(str(p))
            msg = f'The following paths are missing: {msg}'
            logger.warn(msg)
            return

    duplicates = songs_df.duplicated()
    deducplicated_df = songs_df.loc[~duplicates]
    sorted_df = deducplicated_df.sort_values("code")
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    json_path = ASSETS_DIR/'songs.jsonl'
    sorted_df.to_json(
        json_path,
        orient="records",
        lines=True,
        force_ascii=False,
    )
    # TODO: Logging to notify users that jsonl has been saved
    msg = f'Songs successfully saved to {json_path}'
    logger.info(msg)


def main():
    setup_logging()
    #logging.basicConfig(level="INFO")
    #songs_df = uc.loop().run_until_complete(crawl_songs(keep_csv=False))
    songs_df = uc.loop().run_until_complete(crawl_songs())
    #ipdb.set_trace()

    #songs_df = None
    save_songs_in_jsonl(songs_df)
    #pass


if __name__ == "__main__":
    main()
