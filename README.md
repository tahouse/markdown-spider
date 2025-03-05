# Markdown Spider

A flexible, configurable web content spider designed for extracting structured content from websites with different layouts. Perfect for API documentation, creating offline archives, or building custom knowledge bases from multiple sources.

## Features

- **Path-specific rules**: Apply different extraction patterns based on URL paths or domains
- **Content transformation**: Extract content as Markdown or HTML with customizable selectors
- **Parallel processing**: Multi-threaded search for efficiency
- **Configurable**: YAML/TOML configuration files or command-line options
- **Polite crawling**: Built-in rate limiting and respectful bot behavior
- **Cross-domain support**: Follow specific external links with domain-specific rules
- **Intuitive file organization**: Maintains source URL structure in output files

## Installation

```bash
# Clone the repository
git clone https://github.com/tahouse/markdown-spider.git
cd markdown-spider

# Install dependencies
pip install -r requirements.txt
```

### Dependencies

- Python 3.7+
- BeautifulSoup4
- Requests
- Click
- PyYAML
- Markdownify

## Quick Start

### Basic Usage

```bash
# Crawl a website with default settings
python crawl.py --url https://example.com --output-dir ./example_docs
```

### Using a Configuration File

```bash
# Generate a sample configuration file
python crawl.py --generate-config my_config.yaml

# Edit the configuration file with your settings
# Then run the spider with your config
python crawl.py --config my_config.yaml --debug
```

## Configuration

### Command-line Options

```
Options:
  -u, --url TEXT                    Base URL to start crawling from
  -o, --output-dir TEXT             Directory to save files
  -d, --max-depth INTEGER           Maximum crawl depth
  -t, --num-threads INTEGER         Number of worker threads
  -r, --throttle FLOAT              Delay between requests in seconds
  --debug                           Enable debug logging
  --domain-only                     Only crawl URLs on the same domain
  -f, --format [md|html]            Output format
  --user-agent TEXT                 Custom User-Agent string
  --max-children INTEGER            Maximum number of child URLs to process per page
  -c, --config TEXT                 Path to YAML or TOML configuration file
  -g, --generate-config TEXT        Generate a sample configuration file
  --help                            Show this message and exit
```

### Configuration File Format

```yaml
# Base configuration
url: "https://example.com/docs/"
output_dir: "./example_docs"
max_depth: 3
num_threads: 8
throttle: 0.5
same_domain_only: false
file_extension: ".md"

# HTTP settings
headers:
  "User-Agent": "My Web Crawler"
  "Accept-Language": "en-US,en;q=0.9"
timeout: 10

# Path-specific configurations
path_configs:
  - path_prefix: "https://example.com/docs/"
    target_content: ["main", "article.content"]
    ignore_selectors:
      - "nav"
      - "footer"
      - ".sidebar"
    exclude_patterns:
      - "/deprecated/"
      - "/beta/"
    description: "Main documentation"
    
  - path_prefix: "https://api.example.com/"
    target_content: ["div.api-content"]
    ignore_selectors:
      - "header"
      - ".api-sidebar"
    description: "API reference"
```

## Example Use Cases

### Crawling Pulumi GCP Documentation

```yaml
url: "https://www.pulumi.com/registry/packages/gcp/api-docs/"
output_dir: "./pulumi_gcp_docs"
max_depth: 3
num_threads: 12
same_domain_only: false

path_configs:
  - path_prefix: "https://www.pulumi.com/registry/packages/gcp/api-docs/"
    target_content: ["div.docs-main-content"]
    ignore_selectors:
      - "nav"
      - "footer"
      - ".header-nav"
    exclude_patterns:
      - "/typescript/"
      - "/go/"
      - "/csharp/"
    description: "Pulumi GCP API docs"
    
  - path_prefix: "https://cloud.google.com/"
    target_content: [".devsite-article-body", "main", "article"]
    ignore_selectors:
      - "nav"
      - "header"
      - "footer"
    description: "Google Cloud documentation"
```

### Creating a Technical Blog Archive

```yaml
url: "https://techblog.example.com/"
output_dir: "./blog_archive"
max_depth: 2
file_extension: ".md"

path_configs:
  - path_prefix: "https://techblog.example.com/articles/"
    target_content: ["article.post-content"]
    ignore_selectors:
      - "aside"
      - ".author-bio"
      - ".social-share"
    description: "Blog articles"
```

## Advanced Usage

### Following Specific External Links

```bash
python crawl.py --url https://startingsite.com --domain-only false --config external_rules.yaml
```

### Testing with Limited Crawling

```bash
python crawl.py --url https://example.com --max-depth 1 --max-children 2 --debug
```

### Using Different Output Formats

```bash
python crawl.py --url https://example.com --format html
```

## Best Practices

1. **Be respectful**: Use appropriate throttling (delay between requests)
2. **Set descriptive User-Agent**: Identify your spider appropriately
3. **Test with small crawls**: Use `--max-depth` and `--max-children` for testing
4. **Check robots.txt**: Ensure you're allowed to crawl the target site
5. **Update selectors**: Website layouts may change; keep your selectors updated

## Troubleshooting

- **Empty content files**: Check your CSS selectors in `target_content`
- **Missing pages**: Verify URL patterns in `valid_paths` and check `exclude_patterns`
- **Slow crawling**: Adjust `num_threads` and `throttle` values
- **HTTP errors**: Check your `headers` and ensure the site allows crawling

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

Distributed under the Apache 2.0 License. See `LICENSE` for more information.

## Contact

Your Name - [@yourtwitter](https://twitter.com/yourtwitter) - <email@example.com>

Project Link: [https://github.com/yourusername/web-content-spider](https://github.com/yourusername/web-content-spider)

## Acknowledgements

- [BeautifulSoup](https://www.crummy.com/software/BeautifulSoup/)
- [Markdownify](https://github.com/matthewwithanm/python-markdownify)
- [Click](https://click.palletsprojects.com/)

---

Made with ❤️ for web content preservation and knowledge sharing
