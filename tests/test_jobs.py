"""
Tests for the DB-backed Background Queue (job_service).
"""
import pytest
from sqlalchemy.orm import sessionmaker
from app.models.job import Job, JobStatus
from app.services.job_service import enqueue_job, execute_job

# We intentionally DO NOT import from tests.conftest to avoid pytest double-import module bugs
# which can spin up parallel in-memory databases.

def test_enqueue_job(db_session):
    job = enqueue_job(db_session, "test_task", payload={"key": "value"})
    assert job.id is not None
    assert job.name == "test_task"
    assert job.status == JobStatus.pending
    
    # Verify in DB
    db_job = db_session.query(Job).filter(Job.id == job.id).first()
    assert db_job is not None
    assert db_job.payload == {"key": "value"}


def test_execute_job_success(db_session):
    job = enqueue_job(db_session, "success_task", payload={"number": 42})
    db_session.commit()  # Required: factory-opened sessions must see committed data
    
    def mock_processor(db, payload):
        assert payload["number"] == 42
        
    engine_bind = db_session.get_bind()
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine_bind)
    execute_job(factory, job.id, mock_processor)
    
    db_session.refresh(job)
    assert job.status == JobStatus.completed
    assert job.completed_at is not None
    assert job.error is None


def test_execute_job_failure(db_session):
    job = enqueue_job(db_session, "fail_task", payload={})
    db_session.commit()  # Required: factory-opened sessions must see committed data
    
    def failing_processor(db, payload):
        raise ValueError("Something broke!")
        
    engine_bind = db_session.get_bind()
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine_bind)
    execute_job(factory, job.id, failing_processor)
    
    db_session.refresh(job)
    assert job.status == JobStatus.failed
    assert "ValueError: Something broke!" in job.error
    assert job.completed_at is not None
