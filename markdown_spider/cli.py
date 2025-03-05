import sys
import click
import os
import yaml
import logging
from .converter import MarkdownSpider

# Set up logging
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO,
)
logger = logging.getLogger("markdown_spider")


def load_config_file(config_file):
    """Load configuration from a YAML or TOML file"""
    if not os.path.exists(config_file):
        raise click.BadParameter(f"Config file not found: {config_file}")

    file_ext = os.path.splitext(config_file)[1].lower()

    try:
        if file_ext in [".yaml", ".yml"]:
            with open(config_file, "r") as f:
                return yaml.safe_load(f)
        else:
            raise click.BadParameter(f"Unsupported config file format: {file_ext}")
    except Exception as e:
        raise click.BadParameter(f"Failed to parse config file: {str(e)}")


def print_banner():
    banner = """
    🕸️  Markdown Spider 🔽
    --------------------------
    Recursively crawls websites and saves content
    as markdown or HTML files
    """
    print(banner)


@click.command()
@click.option("--url", "-u", help="Base URL to start crawling from")
@click.option("--output-dir", "-o", help="Directory to save files")
@click.option("--max-depth", "-d", type=int, help="Maximum crawl depth")
@click.option("--num-threads", "-t", type=int, help="Number of worker threads")
@click.option("--throttle", "-r", type=float, help="Delay between requests in seconds")
@click.option("--debug", is_flag=True, help="Enable debug logging")
@click.option("--domain-only", is_flag=True, help="Only crawl URLs on the same domain")
@click.option("--format", "-f", type=click.Choice(["md", "html"]), help="Output format")
@click.option("--user-agent", help="Custom User-Agent string")
@click.option(
    "--max-children", type=int, help="Maximum number of child URLs to process per page"
)
@click.option("--config", "-c", help="Path to YAML or TOML configuration file")
@click.option(
    "--generate-config",
    "-g",
    help="Generate a sample configuration file (YAML or TOML)",
)
@click.option(
    "--force-overwrite",
    is_flag=True,
    help="Force overwrite existing files",
)
def main(
    url,
    output_dir,
    max_depth,
    num_threads,
    throttle,
    debug,
    domain_only,
    format,
    user_agent,
    max_children,
    config,
    generate_config,
    force_overwrite,
):
    """Recursively crawl websites and save content as markdown or HTML files.

    Can be configured via command line options or a YAML/TOML config file.
    Path-specific rules can be defined for different domains or URL paths.
    """
    print_banner()

    # Configure logging level
    if debug:
        logger.setLevel(logging.DEBUG)

    # Generate sample configuration if requested
    if generate_config:
        sample_config = {
            "url": "https://www.pulumi.com/registry/packages/gcp/api-docs/",
            "output_dir": "./pulumi_gcp_docs",
            "max_depth": 3,
            "num_threads": 12,
            "throttle": 0.5,
            "same_domain_only": False,
            "file_extension": ".md",
            "max_children_per_page": None,  # Set a number to limit child URLs per page
            "headers": {"User-Agent": "Documentation Spider Bot"},
            "path_configs": [
                {
                    "path_prefix": "https://www.pulumi.com/registry/packages/gcp/api-docs/",
                    "target_content": ["div.docs-main-content"],
                    "ignore_selectors": [
                        "nav",
                        "footer",
                        ".header-nav",
                        ".docs-breadcrumb",
                        "#accordion-package-card",
                        ".pulumi-ai-badge",
                        ".docs-table-of-contents",
                        ".package-details",
                        "#package-details",
                        "title",
                    ],
                    "exclude_patterns": [
                        "/typescript/",
                        "/go/",
                        "/csharp/",
                        "/examples/",
                        "/command-line/",
                        "/changelog/",
                    ],
                    "description": "Pulumi GCP API docs",
                },
                {
                    "path_prefix": "https://cloud.google.com/",
                    "target_content": [".devsite-article-body", "main", "article"],
                    "ignore_selectors": [
                        "nav",
                        "header",
                        "footer",
                        ".devsite-feedback-balloon",
                        ".devsite-book-nav",
                    ],
                    "description": "Google Cloud documentation",
                },
            ],
        }

        if generate_config.endswith((".yaml", ".yml")):
            with open(generate_config, "w") as f:
                yaml.dump(sample_config, f, default_flow_style=False, sort_keys=False)
            click.echo(f"Sample YAML configuration written to {generate_config}")
        else:
            click.echo("Please specify a .yaml or .yml file extension")
        return

    # Load configuration from file if provided
    spider_config = {}
    if config:
        try:
            spider_config = load_config_file(config)
            logger.info(f"Loaded configuration from {config}")
        except click.BadParameter as e:
            click.echo(f"Error: {str(e)}")
            sys.exit(1)

    # Override config with command-line options
    if url:
        spider_config["url"] = url
    if output_dir:
        spider_config["output_dir"] = output_dir
    if max_depth:
        spider_config["max_depth"] = max_depth
    if num_threads:
        spider_config["num_threads"] = num_threads
    if throttle:
        spider_config["throttle"] = throttle
    if domain_only:
        spider_config["same_domain_only"] = domain_only
    if format:
        spider_config["file_extension"] = f".{format}"
    if user_agent:
        if "headers" not in spider_config:
            spider_config["headers"] = {}
        spider_config["headers"]["User-Agent"] = user_agent
    if max_children:
        spider_config["max_children_per_page"] = max_children
    if force_overwrite:
        spider_config["force_overwrite"] = force_overwrite

    # Check for required configuration
    if "url" not in spider_config:
        click.echo("Error: No URL specified. Use --url option or config file.")
        sys.exit(1)
    if "output_dir" not in spider_config:
        spider_config["output_dir"] = "./crawled_content"

    # Set defaults for missing configuration
    spider_config.setdefault("max_depth", 3)
    spider_config.setdefault("num_threads", 8)
    spider_config.setdefault("throttle", 0.5)
    spider_config.setdefault("same_domain_only", False)
    spider_config.setdefault("file_extension", ".md")

    # Create and run the spider
    spider = MarkdownSpider(
        base_url=spider_config["url"],
        output_dir=spider_config["output_dir"],
        path_configs=spider_config.get("path_configs", []),
        max_depth=spider_config["max_depth"],
        num_threads=spider_config["num_threads"],
        throttle=spider_config["throttle"],
        same_domain_only=spider_config["same_domain_only"],
        file_extension=spider_config["file_extension"],
        headers=spider_config.get("headers", {}),
        cookies=spider_config.get("cookies", {}),
        timeout=spider_config.get("timeout", 10),
        max_children_per_page=spider_config.get("max_children_per_page"),
        force_overwrite=spider_config.get("force_overwrite", False),
    )

    pages_crawled = spider.run()

    if pages_crawled > 0:
        click.echo(
            click.style(f"\n✅ Successfully crawled {pages_crawled} pages!", fg="green")
        )
        click.echo(
            click.style(
                f"Content saved to: {os.path.abspath(spider_config['output_dir'])}",
                fg="green",
            )
        )
    else:
        click.echo(
            click.style(
                "\n❌ No pages were crawled. Check your configuration.", fg="red"
            )
        )


if __name__ == "__main__":
    main()
