import json
import logging
import shelve
import urllib.request
import urllib.error
import zipfile
import re
from pathlib import Path
import time
from requests.utils import requote_uri
from concurrent.futures import ThreadPoolExecutor

from ms_client.client import MediaServerRequestError


def remove_forbidden_characters(string: str) -> str:
    """Removes the forbidden characters from a string.
    Args:
        string (str): The requested string.
    Returns:
        str: The requested string without the forbidden characters.
    """
    return re.sub(r"(\\|\/|:|\*|\?|\"|<|>|\|)", " ", string).strip()


class Msc_cache:
    def __init__(self, msc, path, force_reload):
        self.path = path
        self.msc = msc
        self.force_reload = force_reload
        with shelve.open(self.path) as db:
            self.msc_cache_python = dict(db)

    def msc_cache(self, url: str, force_new=False, **kwargs):
        if (url in self.msc_cache_python) and not force_new and not self.force_reload:
            return self.msc_cache_python[url]
        result = self.msc.api(url, **kwargs)
        self.msc_cache_python[url] = result
        with shelve.open(self.path) as db:
            db[url] = result
        return result


class Dl_cache:
    def __init__(self, path):
        self.path = path

        with shelve.open(self.path) as db:
            self.already_dl_cache = dict(db)

    def now_already_dl_cache(self, given_path):
        with shelve.open(self.path) as db:
            db[str(given_path)] = True
        self.already_dl_cache[str(given_path)] = True


class Channel:
    def __init__(self, oid: str, path, msc_cache, server_url: str):
        self.oid: str = oid
        self.msc_cache = msc_cache
        if self.oid == "root":
            self.js = self.msc_cache.msc_cache("channels/content/?local=yes", timeout=(5, 15))
        else:
            url_ = f"channels/content/?parent_oid={self.oid}&content=cvlp&order_by=default&local=yes&_=1676042876656"
            self.js = self.msc_cache.msc_cache(url_)
        self.server_url: str = server_url
        self.path = path
        assert self.js["success"], f"Error on oid {oid}"

    def refresh_js(self):
        if self.oid == "root":
            self.js = self.msc_cache.msc_cache("channels/content/?local=yes", force_new=True, timeout=(5, 15))
        else:
            url_ = f"channels/content/?parent_oid={self.oid}&content=cvlp&order_by=default&local=yes&_=1676042876656"
            self.js = self.msc_cache.msc_cache(url_, force_new=True, timeout=(5, 15))

    def save(self, dl_cache_instance, use_cached_responses: bool = True):
        Path(self.path).mkdir(exist_ok=True)
        logging.info(f"WIP {self.path}")
        if not (self.path / "data.json").exists() or not use_cached_responses:
            with open(str(self.path / "data.json"), "w") as outfile:
                json.dump(self.js, outfile)  # indent=4

        if "videos" in self.js:
            for vid in self.js["videos"]:
                if not vid["ready"]:
                    logging.info(f"{vid['title']} isn't ready")
                    continue
                oid = vid["oid"]
                title = vid["title"]

                path_zip_file = self.path / remove_forbidden_characters(f"{title}.zip")

                js_video_extracted_from_channel = next(filter(lambda x: x["oid"] == oid, self.js["videos"]))
                tumb_url = self.server_url + js_video_extracted_from_channel["thumb"].replace("thumb_catalog.jpg", "thumb.jpg")

                js = self.msc_cache.msc_cache(f"medias/modes/?oid={oid}&html5=webm_ogg_ogv_oga_mp4_m4a_mp3&yt=yt&embed=embed&_=1676051456060")
                annotations_js = self.msc_cache.msc_cache(f"annotations/list/?oid={oid}&local=yes&_=1681659476936")

                if path_zip_file.exists() and dl_cache_instance.already_dl_cache.get(str(path_zip_file), False):
                    # Already DL nothing to do
                    pass
                else:
                    logging.info(f"DL {path_zip_file}")
                    with zipfile.ZipFile(path_zip_file, mode="a") as archive:
                        if not zipfile.Path(archive, "medias.json").exists():
                            archive.writestr("medias.json", json.dumps(js))

                        if not zipfile.Path(archive, "annotations.json").exists():
                            archive.writestr("annotations.json", json.dumps(annotations_js))

                        if not zipfile.Path(archive, "thumb.jpg").exists():
                            try:
                                with urllib.request.urlopen(tumb_url, timeout=(5 * 60)) as response:
                                    archive.writestr("thumb.jpg", response.read())
                            except urllib.error.HTTPError as e:
                                if e.code == 410:
                                    # the thumb url need to be refreshed
                                    self.refresh_js()
                                    logging.critical(
                                        f"Invalid cache has been found and deleted, but the error caused cannot be recovered. Please restart the program."
                                    )
                                raise e
                        # Download the slides
                        with ThreadPoolExecutor(max_workers=2) as executor:
                            for num_slide, annotation in enumerate(annotations_js["annotations"]):
                                if "attachment" in annotation:
                                    if "url" in annotation["attachment"]:
                                        attachment_name = remove_forbidden_characters(f"{num_slide + 1:06}_" + annotation["attachment"]["filename"])
                                        if not zipfile.Path(archive, attachment_name).exists():
                                            executor.submit(
                                                download_attachment_archive,
                                                msc=self.msc_cache.msc,
                                                server_url=self.server_url,
                                                archive=archive,
                                                attachment_name=attachment_name,
                                                annotation=annotation,
                                            )
                    dl_cache_instance.now_already_dl_cache(path_zip_file)

                if len(js["names"]):
                    name = sorted(
                        js["names"],
                        key=lambda name: "format" not in js[name].get("resource", []),
                    )[0]
                    if "format" in js[name]["resource"]:
                        extension = js[name]["resource"]["format"]
                        filename = remove_forbidden_characters(f"{title}.{extension}")
                        definite_path = self.path / filename
                        link = requote_uri(js[name]["resource"]["url"])
                        if not definite_path.exists():
                            download_video(link=link, definite_path=definite_path, js=js, max_retry=10)
                    else:
                        logging.error(f"Impossible to DL {name} - {title} there is no js[name]['resource']['format']\n{js}")
                else:
                    logging.error(f"No name here, don't know what to download ? :\n{js}")

        if "channels" in self.js:
            for channel in self.js["channels"]:
                if channel["slug"] in ("recycle-bin",):
                    continue
                ci = Channel(
                    oid=channel["oid"],
                    path=self.path / Path(remove_forbidden_characters(channel["title"])),
                    msc_cache=self.msc_cache,
                    server_url=self.server_url,
                )
                ci.save(dl_cache_instance=dl_cache_instance, use_cached_responses=use_cached_responses)


def download_video(link: str, definite_path: Path, js, max_retry: int = 10, retry: int = 0):
    video_downloaded = False
    logging.info(f"DL in {js['names'][0]} in {repr(js['names']).replace(' ', '')} {link} {definite_path}")
    try:
        urllib.request.urlretrieve(link, definite_path)
    except Exception as e:
        if retry > max_retry:
            print(f"{retry} retries on {definite_path}")
            raise e
        print(e)
        time.sleep(25)
        video_downloaded = download_video(link=link, definite_path=definite_path, js=js, retry=retry + 1, max_retry=max_retry)
    else:
        video_downloaded = True
    finally:
        if retry == 0 and not video_downloaded:
            logging.info(f"Download canceled, incomplete video file at {definite_path} will be deleted.")
            definite_path.unlink(missing_ok=True)
    assert definite_path.exists()
    return True


def download_attachment_archive(msc, server_url: str, archive, attachment_name, annotation, max_retry: int = 10, retry: int = 0):
    capture_url = server_url + annotation["attachment"]["url"]
    try:
        response_capture = msc.request(
            capture_url, parse_json=False, stream=True, timeout=(5 * 60)
        )  # https://github.com/UbiCastTeam/mediaserver-client/blob/3040b18852f71bc786e04128abeb22e21e9a0634/ms_client/client.py#L95
        if response_capture.status_code == 200:
            archive.writestr(attachment_name, response_capture.read())
        else:
            assert retry < max_retry, f"{response_capture.status_code=}"
            print(f"{capture_url=} {response_capture.status_code=}")
            return download_attachment_archive(
                msc=msc, server_url=server_url, archive=archive, attachment_name=attachment_name, annotation=annotation, max_retry=max_retry, retry=retry + 1
            )
    except MediaServerRequestError as e:
        assert "HTTP 403 error" in repr(e), repr(e)
        logging.warning(f"{repr(e)} on {capture_url}")
