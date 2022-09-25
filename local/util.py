def is_good_html_response(response):
    return response.status_code == 200 and response.headers.get('content-type', '').startswith('text/html')
