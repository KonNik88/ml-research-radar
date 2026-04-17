@echo off
call D:\Anaconda\Scripts\activate.bat ml_radar
cd /d D:\ML\ML_Research_Radar

set LOG_DIR=artifacts\logs
if not exist %LOG_DIR% mkdir %LOG_DIR%

python -m scripts.ingest.run_arxiv_incremental_once --profile medium_scale --advance-state-on-success >> %LOG_DIR%\arxiv_incremental.log 2>&1