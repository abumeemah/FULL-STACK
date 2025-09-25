Changelog for Flask Application URL Configuration
Version: [Current Date - 2025-09-25]
Changed

Modified the handle_redirects function in the Flask application to update the URL redirection logic for the testing environment.
Original Code (for onrender.com redirect):if host.endswith("onrender.com"):
    new_url = request.url.replace("onrender.com", "business.ficoreafrica.com")
    return redirect(new_url, code=301)


Updated Code (for testing environment):if host.endswith("onrender.com"):
    new_url = request.url.replace(host, "business.ficoreafrica.com")
    return redirect(new_url, code=301)


Reason: The original code used a direct string replacement of "onrender.com" with "business.ficoreafrica.com", which could lead to incomplete replacements if the host included additional subdomains or variations. The updated code uses the full host variable to ensure the entire hostname is replaced, improving reliability for redirects in the testing environment (https://ficore-labs-records.onrender.com to https://ficore-labs-records.business.ficoreafrica.com).

Notes for Developers

Purpose: The update was made to support a testing environment. The original URL (https://ficore-labs-records.onrender.com) is the production URL, and the new URL (https://ficore-labs-records.business.ficoreafrica.com) is for testing purposes only.
Revert Instructions: To revert to the production environment, restore the original handle_redirects function as shown below:@app.before_request
def handle_redirects():
    host = request.host
    # Redirect onrender.com to custom domain
    if host.endswith("onrender.com"):
        new_url = request.url.replace("onrender.com", "business.ficoreafrica.com")
        return redirect(new_url, code=301)
    # Redirect www to root domain
    if host.startswith("www."):
        new_url = request.url.replace("www.", "", 1)
        return redirect(new_url, code=301)
    # Redirect ficoreafrica.com to business.ficoreafrica.com
    if host == 'ficoreafrica.com':
        new_url = request.url.replace('ficoreafrica.com', 'business.ficoreafrica.com')
        return redirect(new_url, code=301)


Action Required: If deploying to production, ensure the SERVER_NAME configuration in the create_app function remains set to business.ficoreafrica.com or the appropriate production domain. Verify the environment variable SERVER_NAME in the production environment to avoid unintended redirects.
Testing Environment: The updated code is intended for the testing environment only. Ensure that any deployment to production uses the original redirect logic to maintain access to https://ficore-labs-records.onrender.com.
