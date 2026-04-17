@echo off
call D:\Anaconda\Scripts\activate.bat ml_radar
cd /d D:\ML\ML_Research_Radar

:loop
echo [LOOP] %DATE% %TIME%

python -m scripts.ingest.run_arxiv_incremental_once --profile medium_scale --advance-state-on-success

echo [SLEEP] waiting 30 minutes...
timeout /t 1800 /nobreak

goto loop