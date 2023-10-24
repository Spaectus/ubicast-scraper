import json
import logging
import shelve
import urllib.request
from pathlib import Path
import zipfile
from requests.utils import requote_uri
import re
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
    def __init__(self, msc, path):
        self.path = path
        self.msc = msc
        with shelve.open(self.path) as db:
            self.msc_cache_python = dict(db)

    def msc_cache(self, url: str, force_new=False):
        if (url in self.msc_cache_python) and not force_new:
            return self.msc_cache_python[url]
        result = self.msc.api(url)
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
        self.oid = oid
        self.msc_cache = msc_cache
        if oid == "root":
            self.js = msc_cache.msc_cache("channels/content/?local=yes", timeout=(5, 15))
        else:
            url_ = f"channels/content/?parent_oid={self.oid}&content=cvlp&order_by=default&local=yes&_=1676042876656"
            self.js = msc_cache.msc_cache(url_)
        self.server_url = server_url
        self.path = path
        assert self.js["success"], f"Error on oid {oid}"

    def getVideosOidList(self):
        res = []
        if "videos" in self.js:
            res = self.js["videos"]
        if "channels" in self.js:
            for channel in self.js["channels"]:
                ci = Channel(
                    channel["oid"],
                    path=self.path / Path(remove_forbidden_characters(channel["title"])),
                    msc_cache=self.msc_cache,
                    server_url=self.server_url,
                )
                res.extend(ci.getVideosOidList())
        return res

    def save(self, dl_cache_instance):
        Path(self.path).mkdir(exist_ok=True)
        logging.info(f"WIP {self.path}")
        if not (self.path / "data.json").exists() or 1:
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

                js_video_extracted_from_channel = next(
                    filter(lambda x: x["oid"] == oid, self.js["videos"])
                )
                tumb_url = self.server_url + js_video_extracted_from_channel[
                    "thumb"
                ].replace("thumb_catalog.jpg", "thumb.jpg")

                js = self.msc_cache.msc_cache(
                    f"medias/modes/?oid={oid}&html5=webm_ogg_ogv_oga_mp4_m4a_mp3&yt=yt&embed=embed&_=1676051456060"
                )
                annotations_js = self.msc_cache.msc_cache(
                    f"annotations/list/?oid={oid}&local=yes&_=1681659476936"
                )

                if path_zip_file.exists() and dl_cache_instance.already_dl_cache.get(
                        str(path_zip_file), False
                ):
                    # Already DL nothing to do
                    pass
                else:
                    logging.info(f"DL {path_zip_file}")
                    with zipfile.ZipFile(path_zip_file, mode="a") as archive:
                        if not zipfile.Path(archive, "medias.json").exists():
                            archive.writestr("medias.json", json.dumps(js))

                        if not zipfile.Path(archive, "annotations.json").exists():
                            archive.writestr(
                                "annotations.json", json.dumps(annotations_js)
                            )

                        if not zipfile.Path(archive, "thumb.jpg").exists():
                            with urllib.request.urlopen(
                                    tumb_url, timeout=(5 * 60)
                            ) as response:
                                archive.writestr("thumb.jpg", response.read())

                        # Download the slides
                        with ThreadPoolExecutor(max_workers=5) as executor:
                            for num_slide, annotation in enumerate(
                                    annotations_js["annotations"]
                            ):
                                if "attachment" in annotation:
                                    if "url" in annotation["attachment"]:
                                        attachment_name = remove_forbidden_characters(
                                            f"{num_slide + 1:06}_"
                                            + annotation["attachment"]["filename"]
                                        )
                                        if not zipfile.Path(
                                                archive, attachment_name
                                        ).exists():
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
                            video_downloaded = False
                            try:
                                logging.info(
                                    f"DL in {js['names'][0]} in {repr(js['names']).replace(' ', '')} {link} {definite_path}"
                                )
                                urllib.request.urlretrieve(link, definite_path)
                                video_downloaded = True
                            finally:
                                if not video_downloaded:
                                    logging.info(
                                        f"Download canceled, incomplete video file at {definite_path} will be deleted."
                                    )
                                    definite_path.unlink(missing_ok=True)
                    else:
                        logging.error(
                            f"Impossible to DL {name} - {title} there is no js[name]['resource']['format']\n{js}"
                        )
                else:
                    logging.error(
                        f"No name here, don't know what to download ? :\n{js}"
                    )

        if "channels" in self.js:
            for channel in self.js["channels"]:
                if channel["slug"] == "recycle-bin":
                    continue
                ci = Channel(
                    oid=channel["oid"],
                    path=self.path / Path(remove_forbidden_characters(channel["title"])),
                    msc_cache=self.msc_cache,
                    server_url=self.server_url,
                )
                ci.save(dl_cache_instance=dl_cache_instance)


def download_attachment_archive( msc, server_url: str, archive, attachment_name, annotation):
    capture_url = server_url + annotation["attachment"]["url"]
    try:
        response_capture = msc.request(
            capture_url, parse_json=False, stream=True, timeout=(5 * 60)
        )  # https://github.com/UbiCastTeam/mediaserver-client/blob/3040b18852f71bc786e04128abeb22e21e9a0634/ms_client/client.py#L95
        if response_capture.status_code == 200:
            archive.writestr(attachment_name, response_capture.read())
        else:
            assert 0, f"{response_capture.status_code=}"
    except MediaServerRequestError as e:
        assert "HTTP 403 error" in repr(e), repr(e)
