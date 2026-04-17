@echo off
call D:\Anaconda\Scripts\activate.bat ml_radar
cd /d D:\ML\ML_Research_Radar

python -m scripts.ingest.merge_arxiv_incremental_batches