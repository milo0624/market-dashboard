name: market-update
on:
  schedule:
    - cron: '0 0 * * 1-5'
  workflow_dispatch:
permissions:
  contents: write
  pages: write
  id-token: write
jobs:
  run:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: install-sdk
        run: |
          wget -q "https://www.fbs.com.tw/TradeAPI_SDK/fubon_binary/fubon_neo-2.2.8-cp37-abi3-manylinux_2_17_x86_64.manylinux2014_x86_64.zip" -O sdk.zip
          unzip -q sdk.zip
          pip install fubon_neo-2.2.8-cp37-abi3-manylinux_2_17_x86_64.manylinux2014_x86_64.whl requests
      - name: fetch
        env:
          FUBON_ID: ${{ secrets.FUBON_ID }}
          FUBON_API_KEY: ${{ secrets.FUBON_API_KEY }}
          FUBON_SECRET_KEY: ${{ secrets.FUBON_SECRET_KEY }}
          FUBON_CERT_B64: ${{ secrets.FUBON_CERT_B64 }}
          FUBON_CERT_PW: ${{ secrets.FUBON_CERT_PW }}
        run: python fetch_market.py
      - name: commit
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add public/data.json
          git diff --staged --quiet || git commit -m "data update"
          git push
      - uses: peaceiris/actions-gh-pages@v3
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          publish_dir: ./public
          keep_files: true
