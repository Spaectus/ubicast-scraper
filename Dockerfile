FROM python:3.12-alpine

WORKDIR /xscraper
COPY Pipfile Pipfile.lock ./

RUN pip install --no-cache-dir micropipenv[toml] \
  && micropipenv install --deploy \
  && pip uninstall -y micropipenv[toml]

RUN mkdir output

COPY *.py .

CMD ["python3", "main.py", "./output"]