import httpx
from openai import APIConnectionError, BadRequestError
from app.api.error_handlers import log_analysis_failure
from app.services.contour_extraction import ContourExtractionError


def test_logs_provider_status_without_sensitive_error_body(caplog):
    request = httpx.Request('POST', 'https://api.openai.com/v1/responses', headers={'Authorization': 'Bearer secret-key'})
    provider = BadRequestError('private image contents', response=httpx.Response(400, request=request, headers={'x-request-id': 'req_test123'}), body={'secret': 'private image contents'})
    error = ContourExtractionError('failed')
    error.__cause__ = provider
    log_analysis_failure(error)
    assert 'provider_status=400' in caplog.text
    assert 'req_test123' in caplog.text
    assert 'BadRequestError' in caplog.text
    assert 'private image contents' not in caplog.text
    assert 'secret-key' not in caplog.text


def test_logs_network_cause_without_sensitive_details(caplog):
    provider = APIConnectionError(request=httpx.Request('POST', 'https://api.openai.com/v1/responses'))
    provider.__cause__ = httpx.ConnectError('sensitive network details')
    error = ContourExtractionError('failed')
    error.__cause__ = provider
    log_analysis_failure(error)
    assert 'APIConnectionError -> ConnectError' in caplog.text
    assert 'sensitive network details' not in caplog.text
