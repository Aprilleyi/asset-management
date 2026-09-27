from apscheduler.schedulers.background import BackgroundScheduler

from app.tasks.scheduler import create_scheduler


scheduler: BackgroundScheduler = create_scheduler()
