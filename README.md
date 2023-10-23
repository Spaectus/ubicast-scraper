# Scraper for Polytechnique's Ubicast instance

This tool retrieves the entire content of the [enseignement.medias.polytechnique.fr](https://enseignement.medias.polytechnique.fr/) website, i.e. all videos, including thumbnails and slides.
You must have an account and retrieve your ubicast api key here : https://enseignement.medias.polytechnique.fr/authentication/account-settings/ in order to use this tool.

## With Docker

```shell
docker build -t xscraper .
docker run -v /path/to/folder:/xscraper/output -e "UBICAST_API_KEY=XXXXX-XXXXX-XXXXX-XXXXX-XXXXX" -ti --rm xscraper
```

## Without Docker

1. Specify your `UBICAST_API_KEY` in a `.env` file. The `.env` file must be at the root folder of the project, next to `Pipfile.lock`.
```text
UBICAST_API_KEY=XXXXX-XXXXX-XXXXX-XXXXX-XXXXX
```
2. Run in the project's folder :
```shell
pip install pipenv
pipenv install --ignore-pipfile
pipenv run python main.py path/to/folder #where scraped files will be stored
```