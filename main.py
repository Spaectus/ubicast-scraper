import argparse
import logging
import os
import sys
import tempfile
import json
from pathlib import Path

from ms_client.client import MediaServerClient

from lib import Channel, Msc_cache, Dl_cache

if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="Scrape an ubicast instance. An ubicast api key must be given via the UBICAST_API_KEY environment variable."
    )
    parser.add_argument(
        "path",
        help="Path of the folder in which you wish to have the scraped files. The folder must exist.",
    )
    args = parser.parse_args()

    try:
        if not Path(args.path).exists():
            raise ValueError(f"Path {Path(args.path)} does not exists")
    except Exception as e:
        logging.critical(repr(e))
        sys.exit(1)

    rpath = Path(args.path)

    server_url = "https://enseignement.medias.polytechnique.fr"
    assert (
            "UBICAST_API_KEY" in os.environ
    ), f"The UBICAST_API_KEY environment variable is not defined. An ubicast api key must be given via the UBICAST_API_KEY environment variable."

    config_media = {
        "API_KEY": os.environ["UBICAST_API_KEY"],
        "CLIENT_ID": "python-api-client",
        "PROXIES": {"http": "", "https": ""},
        "SERVER_URL": server_url,
        "UPLOAD_CHUNK_SIZE": 5242880,
        "VERIFY_SSL": True,
    }

    path_msc_cache = str((rpath / Path("cache_msc")).absolute())
    path_already_dl_cache = str(rpath / "already_dl_cache")

    dl_cache = Dl_cache(path=path_already_dl_cache)

    with tempfile.NamedTemporaryFile(mode="w", delete=True, delete_on_close=False, encoding="utf-8") as fp:
        fp.write(json.dumps(config_media))
        fp.close()
        msc = MediaServerClient(local_conf=Path(fp.name))

    msc_cache = Msc_cache(msc=msc, path=path_msc_cache)

    root_channel = Channel(oid="root", path=rpath, msc_cache=msc_cache, server_url=server_url)

    root_channel.save(dl_cache_instance=dl_cache)
