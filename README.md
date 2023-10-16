# Scraper for Polytechnique's Ubicast instance

This tool is for scraping the content this website https://enseignement.medias.polytechnique.fr/. You must have an account and retrieve your ubicast api key here : https://enseignement.medias.polytechnique.fr/authentication/account-settings/ in order to use this tool.

## Usage

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