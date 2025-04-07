import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin, urlencode
import time
import functools
import argparse

delaySeconds = 0

VERSION = "0.1.0"

def delay():
    time.sleep(delaySeconds)

def rate_limited():
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            delay()
            return func(*args, **kwargs)
        return wrapper
    return decorator

def save_items(items):
    with open("items.txt", "a") as file:
        file.writelines(item + "\n" for item in items)

def get_api_url(wiki_url):
    """Get the MediaWiki API URL from a wiki."""
    # Check if URL already contains api.php
    if "api.php" in wiki_url:
        return wiki_url
    
    # Otherwise, try parsing <link rel="EditURI">
    print("Trying to find the API from the EditURI")
    response = requests.get(wiki_url)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Try to find <link rel="EditURI">
    link = soup.find('link', rel="EditURI")
    if link:
        api_url = link['href']
        # Remove query params from API URL
        return api_url.split('?')[0]
    
    delay()

    # Otherwise, fallback to the CSS file method
    print("Trying to find the API from load.php")
    css_link = soup.find('link', {'rel': 'stylesheet'})
    if css_link and 'href' in css_link.attrs:
        css_url = css_link['href']
        parsed_url = urlparse(css_url)
        api_url = f"{parsed_url.scheme}://{parsed_url.netloc}/api.php"
        return api_url
    
    return None

@rate_limited()
def get_site_info(api_url):
    """Get general site information including namespaces."""
    params = {
        'action': 'query',
        'meta': 'siteinfo',
        'siprop': 'general|namespaces',
        'format': 'json'
    }
    response = requests.get(api_url, params=params)
    data = response.json()
    
    site_info = data['query']['general']
    namespaces = data['query']['namespaces']
    
    return site_info, namespaces


def get_all_pages(api_url, gapnamespace=0):
    """Get all pages for a namespace with URLs (paginated)."""
    params = {
        'action': 'query',
        'generator': 'allpages',
        'gapnamespace': gapnamespace,
        'gaplimit': '50',
        'prop': 'info',
        'inprop': 'url',
        'format': 'json',
        'continue': '' # required for modern continue on MW 1.21-1.25, see https://www.mediawiki.org/wiki/API:Continue 
        }
    
    all_pages = []
    while True:
        response = requests.get(api_url, params=params)
        data = response.json()
        
        if 'query' in data:
            for page_id, page_info in data['query']['pages'].items():
                all_pages.append(f"mediawiki-article:{page_info['fullurl']}")
        print(f"Got {len(all_pages)} article items...")
        
        delay()

        # Check if there is a "continue" field to paginate
        # 
        if 'continue' in data:
            params.update(data['continue'])
        elif 'query-continue' in data: 
            # required for continue on MW <1.21
            # this is not an ideal implementation of continue, but we only ever need to paginate
            # one generator, so should be okay
            params.update(data['query-continue']['categories'])
        else:
            break
    
    return all_pages


def get_all_images(api_url):
    """Get all media (images) with URLs."""
    params = {
        'action': 'query',
        'list': 'allimages',
        'aiprop': 'url',
        'ailimit': '50',
        'format': 'json',
        'continue': '' 
    }
    
    all_images = []
    while True:
        response = requests.get(api_url, params=params)
        data = response.json()
        
        if 'query' in data:
            for image in data['query']['allimages']:
                all_images.append(f"mediawiki-media:{image['url']}")
       
        print(f"Found {len(all_images)} media items...")
        delay()
        # Check if there is a "continue" field to paginate
        if 'continue' in data:
            params.update(data['continue'])
        elif 'query-continue' in data:
            params.update(data['query-continue']['categories'])
        else:
            break

        
    
    return all_images

@rate_limited()
def get_special_pages(api_url, template_url):
    """Get all special pages and their aliases."""
    params = {
        'action': 'query',
        'meta': 'siteinfo',
        'siprop': 'specialpagealiases',
        'format': 'json'
    }
    response = requests.get(api_url, params=params)
    data = response.json()
    
    special_pages_raw = data['query']['specialpagealiases']
    special_pages = set()
    for entry in data['query']['specialpagealiases']:
        special_pages.add(entry['realname'])
        special_pages.update(entry.get('aliases', []))
    
    items = set()
    for special_page in special_pages:
        items.add(f"mediawiki-special:{template_url.replace('$1',f'Special:{special_page}')}")
    
    print(f"Found {len(items)} special pages...")

    return items


def main(wiki_url):
    # Get the API URL
    print("Trying to find the wiki API URL")
    api_url = get_api_url(wiki_url)
    if not api_url:
        print("Failed to find the API URL.")
        return
    
    print(f"Using API URL: {api_url}")
    

    # Get site info and namespaces
    site_info, namespaces = get_site_info(api_url)
    server_url = urljoin(api_url, site_info['server'])
    template_url = urljoin(server_url, site_info['articlepath'])
    print(f"Found {len(namespaces) - 2} namespaces")
    print(f"Site page URL template: {template_url}")
    
    # Get all pages
    for ns in namespaces.values():
        if ns['id'] < 0:
            # Fake namespaces for media and special pages that never actually have articles
            continue

        print(f"\nGetting pages in namespace {ns['id']} ({ns.get('canonical', '')})")
        pages = get_all_pages(api_url, gapnamespace=ns['id'])
        save_items(pages) 

    # Get all images
    print("\nFinding media items")
    save_items(get_all_images(api_url))
    
    # Get special pages
    print("\nFinding special pages")
    save_items(get_special_pages(api_url, template_url))
        


if __name__ == "__main__":
    print("mediawiki-item-discovery.py v" + VERSION)
    parser = argparse.ArgumentParser(prog="MediaWiki item discovery")
    parser.add_argument("url")
    parser.add_argument("--delay", )
    args = parser.parse_args()
    main(args.url)