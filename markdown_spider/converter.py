#!/usr/bin/env python3

import os
import sys
import tempfile
import types
import uuid
import requests
import logging
import queue
import threading
import time
import urllib.parse
import re
from bs4 import BeautifulSoup, Tag
from markdownify import markdownify, MarkdownConverter, chomp
import click
import yaml

# Set up logging
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


class BetterConverter(MarkdownConverter):
    """
    Extended MarkdownConverter that handles GitHub Flavored Markdown tables
    Based on the turndown-plugin-gfm table handling logic
    """

    def __init__(self, **options):
        super().__init__(**options)
        # Initialize properties
        self.tag_value_selections = options.get("tag_value_selections", {})
        self.pulumi_language = options.get("pulumi_language", None)

    def convert_table(self, el, text, convert_as_inline):
        if self.should_skip_table(el):
            return text

        if self.should_keep_table_html(el):
            return f"\n\n{el.prettify()}\n\n"

        # Remove any blank lines
        text = text.replace("\n\n", "\n")

        # Get column count and alignments
        col_alignments = self.get_column_alignments(el)

        # Build header row if needed
        header = ""
        if not self.has_header_row(el):
            header = "|" + "|".join(" " * 3 for _ in range(len(col_alignments))) + "|\n"
            header += (
                "|"
                + "|".join(self.get_alignment_marker(align) for align in col_alignments)
                + "|"
            )

        caption = ""
        if el.find("caption"):
            caption = el.find("caption").get_text().strip() + "\n\n"

        table_content = f"{header}{text}".strip()
        return f"\n\n{caption}{table_content}\n\n"

    def convert_tr(self, el, text, convert_as_inline):
        if self.should_skip_table(el.find_parent("table")):
            return text

        cells = el.find_all(["td", "th"])
        separator = ""

        # Add separator row after header
        if self.is_header_row(el):
            alignments = self.get_column_alignments(el.find_parent("table"))
            separator = (
                "\n|"
                + "|".join(self.get_alignment_marker(align) for align in alignments)
                + "|"
            )

        row = "|" + "|".join(self.convert_cell(cell) for cell in cells) + "|"
        return row + separator + "\n"

    def convert_cell(self, el):
        colspan = int(el.get("colspan", 1))
        content = super().process_tag(el, convert_as_inline=True)

        # Clean up content
        content = content.replace("\n", " ").strip()
        content = content.replace("|", "\\|")  # Escape pipe characters

        # Pad short content
        while len(content) < 3:
            content += " "

        # Handle colspan
        if colspan > 1:
            content += " |" + " " * 3 * (colspan - 1)

        return f" {content} "

    def should_skip_table(self, table):
        """Determine if table should be skipped (rendered as plain text)"""
        if not table:
            return True

        rows = table.find_all("tr")
        if not rows:
            return True

        # Skip single-cell tables
        if len(rows) == 1 and len(rows[0].find_all(["td", "th"])) <= 1:
            return True

        return False

    def should_keep_table_html(self, table):
        """Determine if table should be kept as HTML"""
        # Keep tables containing block elements that GFM tables don't support
        block_elements = [
            "table",
            "pre",
            "code",
            "blockquote",
            "ul",
            "ol",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "hr",
        ]

        for tag in block_elements:
            if table.find(tag):
                return True

        return False

    def is_header_row(self, tr):
        """Determine if tr is a header row"""
        parent = tr.parent.name if tr.parent else None

        # If parent is thead, it's a header
        if parent == "thead":
            return True

        # If it's the first row in table/tbody
        if tr == tr.parent.find("tr"):
            if parent == "table" or (
                parent == "tbody" and not tr.find_previous_sibling("thead")
            ):
                # Check if all cells are th
                cells = tr.find_all(["td", "th"])
                return all(cell.name == "th" for cell in cells)

        return False

    def has_header_row(self, table):
        """Check if table has a header row"""
        first_row = table.find("tr")
        return first_row and self.is_header_row(first_row)

    def get_column_alignments(self, table):
        """Get alignment for each column"""
        alignments = []
        if not table:
            return alignments

        # Get all rows
        rows = table.find_all("tr")
        if not rows:
            return alignments

        # Get max column count
        max_cols = max(len(row.find_all(["td", "th"])) for row in rows)

        # For each column, determine alignment
        for col_idx in range(max_cols):
            alignment = self.get_column_alignment(table, col_idx)
            alignments.append(alignment)

        return alignments

    def get_column_alignment(self, table, col_idx):
        """Get alignment for a specific column"""
        alignments = {"left": 0, "right": 0, "center": 0, "": 0}

        for row in table.find_all("tr"):
            cells = row.find_all(["td", "th"])
            if col_idx < len(cells):
                cell = cells[col_idx]
                # Try to get alignment from align attribute
                cell_align = cell.get("align", "").lower()

                # If not found, try to extract from style attribute
                if not cell_align:
                    style = cell.get("style", "")
                    align_match = re.search(
                        r"text-align\s*:\s*(left|right|center)", style, re.IGNORECASE
                    )
                    if align_match:
                        cell_align = align_match.group(1).lower()

                # Only count if it's one of our known alignments
                if cell_align in alignments:
                    alignments[cell_align] += 1

        # Return most common alignment or empty string if no alignments found
        return (
            max(alignments.items(), key=lambda x: x[1])[0]
            if any(alignments.values())
            else ""
        )

    def get_alignment_marker(self, alignment):
        """Get markdown alignment marker"""
        markers = {"left": ":---", "right": "---:", "center": ":---:", "": "---"}
        return markers.get(alignment, "---")

    def convert_code(self, el, text, convert_as_inline):
        """
        Strip markdown formatting from code blocks before letting parent handle the rest
        """
        if el.parent.name == "pre":
            # For code blocks, strip out any markdown links and formatting
            text = re.sub(r"\[(.*?)\]\(.*?\)", r"\1", text)
            text = re.sub(r"(\*\*|__|\*|_|~~)", "", text)

        return super().convert_code(el, text, convert_as_inline)

    def convert_pre(self, el, text, convert_as_inline):
        """
        Strip markdown formatting from pre blocks before letting parent handle the rest
        """
        if text:
            # Strip any markdown links or formatting
            text = re.sub(r"\[(.*?)\]\(.*?\)", r"\1", text)
            text = re.sub(r"(\*\*|__|\*|_|~~)", "", text)

        return super().convert_pre(el, text, convert_as_inline)

    def convert_dl(self, el, text, convert_as_inline):
        """Handle definition lists, with special case for Pulumi resources"""
        # Check if this is a Pulumi resource properties list
        if el.get("class") and "resources-properties" in el.get("class"):
            return self.convert_pulumi_properties(el)

        # Default dl handling if not Pulumi specific
        # Process dt/dd pairs with basic markdown formatting
        result = "\n\n"
        for dt in el.find_all("dt"):
            term = self.process_tag(dt, convert_as_inline=True)

            # Find the next dd sibling
            dd = dt.find_next_sibling("dd")
            if dd:
                definition = self.process_tag(dd, convert_as_inline=False)
                result += f"**{term.strip()}**: {definition.strip()}\n\n"
            else:
                result += f"**{term.strip()}**\n\n"

        return result

    def convert_pulumi_properties(self, dl_element):
        """Convert Pulumi resource properties to a nice markdown table"""
        # Create table header
        table = "| Property | Type | Description |\n"
        table += "|---------|------|-------------|\n"

        # Process each dt/dd pair
        dt_elements = dl_element.find_all("dt")

        for dt in dt_elements:
            # Get property name (handle nested spans)
            property_name = ""
            property_link = dt.find("a")
            if property_link:
                property_name = property_link.get_text().strip()
            else:
                property_name = dt.get_text().strip()

            # Get property type
            property_type = ""
            type_span = dt.find("span", class_="property-type")
            if type_span:
                property_type = type_span.get_text().strip()

            # Get description from the dd element that follows
            description = ""
            dd = dt.find_next("dd")
            if dd:
                description = dd.get_text().strip().replace("\n", " ")

            # Add row to table
            table += f"| {property_name} | {property_type} | {description} |\n"

        return f"\n\n{table}\n\n"

    def convert_div(self, el, text, convert_as_inline):
        """Handle div elements, including Pulumi-choosable"""
        # Check if this is a Pulumi choosable element
        if el.find("pulumi-choosable"):
            # Find the active content within pulumi-choosable
            active_div = el.find("div", class_="active")
            if active_div:
                return self.process_tag(active_div, convert_as_inline)

        # Default div handling
        return text if not convert_as_inline else " "

    def convert_pulumi_choosable(self, el, text, convert_as_inline):
        """Handle choosable elements with type and values attributes"""
        if el.has_attr("type") and el.has_attr("values"):
            tag_type = el.get("type", "")
            values = [v.strip() for v in el.get("values", "").split(",")]

            # If we have a language selection and this is a language tag
            if (
                hasattr(self, "pulumi_language")
                and self.pulumi_language
                and tag_type == "language"
            ):
                # If our language matches one of the values for this tag
                if self.pulumi_language in values:
                    return f"\n\n#### {self.pulumi_language}\n\n{text}\n\n"
                else:
                    return ""  # Skip this content

            # If no selection is specified, show with a header
            display_value = values[0].capitalize() if values else "Example"
            return f"\n\n#### {display_value}\n\n{text}\n\n"

        # Default handling
        return text

    # Since hyphenated tag names aren't directly supported, we need to handle them differently
    # This overrides the __getattr__ method to catch calls like convert_pulumi-choosable
    def __getattr__(self, attr):
        # First check the parent's __getattr__ for heading conversions
        try:
            return super().__getattr__(attr)
        except AttributeError:
            # If the attribute starts with 'convert_pulumi-'
            if attr.startswith("convert_pulumi-"):
                # Extract the tag name after 'convert_'
                tag_name = attr[len("convert_") :]
                # Replace hyphens with underscores for method lookup
                method_name = f"convert_{tag_name.replace('-', '_')}"
                # Try to find the method
                if hasattr(self, method_name):
                    return getattr(self, method_name)
            # If nothing found, raise the original error
            raise AttributeError(attr)

    # Handle pulumi-chooser tags - method name uses underscore instead of hyphen
    def convert_pulumi_chooser(self, el, text, convert_as_inline):
        """Handle pulumi-chooser elements that control language selection"""
        # This element mainly controls the UI for selection
        # Return empty string as this tag doesn't have content to display
        return ""


class MarkdownSpider:
    def __init__(
        self,
        base_url,
        output_dir,
        path_configs=None,
        max_depth=3,
        num_threads=8,
        throttle=0.5,
        same_domain_only=False,
        file_extension=".md",
        headers=None,
        cookies=None,
        timeout=10,
        max_children_per_page=None,
        force_overwrite=False,
    ):
        self.base_url = base_url
        self.output_dir = output_dir
        self.max_depth = max_depth
        self.num_threads = num_threads
        self.throttle = throttle
        self.same_domain_only = same_domain_only
        self.file_extension = file_extension
        self.timeout = timeout
        self.max_children_per_page = max_children_per_page
        self.already_crawled = set()
        self.base_domain = urllib.parse.urlparse(base_url).netloc
        self.force_overwrite = force_overwrite

        # Initialize path configs
        self.path_configs = path_configs or []
        # Add default config if no paths are specified
        if not self.path_configs:
            self.path_configs.append(
                {
                    "path_prefix": "",  # Match all paths
                    "target_content": ["body"],
                    "ignore_selectors": [],
                    "exclude_patterns": [],
                    "include_patterns": [],
                    "description": "Default configuration",
                }
            )

        # Headers for requests
        self.headers = headers or {}
        if "User-Agent" not in self.headers:
            self.headers["User-Agent"] = (
                "Generic Web Crawler (https://github.com/yourusername/web-spider)"
            )

        # Cookies for requests
        self.cookies = cookies or {}

        # Create base directory if it doesn't exist
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        # Print path configurations for debugging
        logger.debug("Path configurations:")
        for i, config in enumerate(self.path_configs):
            logger.debug(
                f"  {i+1}. {config.get('description', 'Unnamed config')}: {config.get('path_prefix', '/')}"
            )

    def _get_code_language(self, element):
        """Recursively check element and its children for language specification."""

        def check_element(el):
            # Check if element is a Tag (not a NavigableString or other non-tag element)
            if not isinstance(el, Tag):
                return None

            # Check class attribute
            if el.has_attr("class"):
                classes = el["class"]
                if isinstance(classes, str):
                    classes = [classes]
                for cls in classes:
                    if cls.startswith("language-"):
                        return cls.replace("language-", "")

            # Check data-lang attribute
            if el.has_attr("data-lang"):
                return el["data-lang"]

            # Recursively check children
            for child in el.children:
                if hasattr(child, "name"):  # Only process tag elements
                    result = check_element(child)
                    if result:
                        return result

            return None

        return check_element(element)

    def find_config_for_url(self, url):
        """Find the appropriate configuration for a given URL"""
        for config in self.path_configs:
            path_prefix = config.get("path_prefix", "")
            if path_prefix and url.startswith(path_prefix):
                return config

        # Return the first config with empty path_prefix as default, or the first config
        for config in self.path_configs:
            if not config.get("path_prefix"):
                return config
        return self.path_configs[0]

    def normalize_url(self, url):
        """Normalize a URL by removing trailing slashes and fragments"""
        parsed = urllib.parse.urlparse(url)
        return urllib.parse.urlunparse(
            (parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), None, None, None)
        )

    def should_crawl_url(self, url, is_relative=False):
        """Determine if a URL should be crawled based on domain and path restrictions"""
        parsed_url = urllib.parse.urlparse(url)

        # Check domain restriction
        if self.same_domain_only and parsed_url.netloc != self.base_domain:
            if is_relative:
                logger.debug(
                    f"❌ DOMAIN RESTRICTION: {url} - not in {self.base_domain}"
                )
            return False

        # Check if URL matches any path prefix configuration
        url_matched = False
        matched_config = None
        matched_prefix = None

        for config in self.path_configs:
            path_prefix = config.get("path_prefix", "")

            # Empty path_prefix matches everything (default config)
            if not path_prefix:
                url_matched = True
                matched_config = config
                matched_prefix = "(empty prefix)"
                if is_relative:
                    logger.debug(
                        f"✅ PATH MATCH: {url} - matched empty path prefix (default)"
                    )
                break

            # Check if URL starts with path_prefix
            if url.startswith(path_prefix):
                url_matched = True
                matched_config = config
                matched_prefix = path_prefix
                if is_relative:
                    logger.debug(f"✅ PATH MATCH: {url} - matched prefix {path_prefix}")
                break

        if not url_matched:
            if is_relative:
                logger.debug(f"❌ NO PATH MATCH: {url}")
                logger.debug(f"  Available prefixes:")
                for config in self.path_configs:
                    logger.debug(f"  - {config.get('path_prefix', '(empty)')}")
            return False

        if matched_config is None:
            return False  # Add this check to prevent NoneType errors

        # Apply exclude patterns from the matched config
        exclude_patterns = matched_config.get("exclude_patterns", [])
        for pattern in exclude_patterns:
            if re.search(pattern, url):
                if is_relative:
                    logger.debug(f"❌ EXCLUDE PATTERN: {url} - matched {pattern}")
                return False

        # Apply include patterns from the matched config
        include_patterns = matched_config.get("include_patterns", [])
        if include_patterns and not any(
            re.search(pattern, url) for pattern in include_patterns
        ):
            if is_relative:
                logger.debug(f"❌ INCLUDE PATTERN: {url} - did not match any pattern")
                logger.debug(f"  Available include patterns:")
                for pattern in include_patterns:
                    logger.debug(f"  - {pattern}")
            return False

        # URL passed all filters
        if is_relative:
            logger.debug(f"✅ ALL CHECKS PASSED: {url}")
            logger.debug(
                f"  Using config: {matched_config.get('description', 'unnamed')}"
            )
            logger.debug(f"  With prefix: {matched_prefix}")

        return True

    def format_markdown(self, text: str) -> str:
        """Parse and re-render markdown with Marko"""
        # output = re.sub(r"```\n```", "```\n\n```", output)
        output = re.sub(
            r"```\s*\n```", "```\n\n```", text
        )  # Add blank lines between adjacent code blocks

        # Write the raw markdown to a temporary file
        crawl_temp = "crawl-temp"
        temp_dir = tempfile.gettempdir()
        temp_file = os.path.join(temp_dir, f"crawl-markdown-{uuid.uuid4()}.md")
        with open(temp_file, "w", encoding="utf-8") as f:
            f.write(output)

        # Run markdownlint-cli2 to fix the markdown
        import subprocess
        import glob

        try:
            result = subprocess.run(
                ["npx", "markdownlint-cli2", "--fix", temp_file],
                check=False,  # We intentionally don't use check=True here to allow non-zero exit codes
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=10,  # Add timeout to prevent hanging
            )

            # Log the output but don't fail if it's just linting errors
            if result.returncode != 0:
                logger.debug(f"Markdownlint exited with code {result.returncode}")
                logger.debug(
                    f"stderr: {result.stderr.decode('utf-8', errors='replace')}"
                )
        except subprocess.SubprocessError as e:
            # This catches actual subprocess failures like missing commands or timeout
            logger.error(f"Failed to run markdownlint: {str(e)}")
            # return output

        # Read the fixed content
        with open(temp_file, "r", encoding="utf-8") as f:
            fixed_content = f.read()

        # Remove the temporary file
        if os.path.exists(temp_file):
            os.remove(temp_file)

        return fixed_content

    def crawl_url(self, url, file_path):
        """Crawl a URL and extract content"""
        if url in self.already_crawled:
            return []

        try:
            logger.debug(f"Crawling: {url}")
            response = requests.get(
                url, headers=self.headers, cookies=self.cookies, timeout=self.timeout
            )
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Request error for {url}: {e}")
            return []

        if response.status_code != 200:
            logger.error(f"❌ HTTP {response.status_code} for {url}")
            return []

        content_type = response.headers.get("Content-Type", "")
        if (
            "text/html" not in content_type
            and "application/xhtml+xml" not in content_type
        ):
            logger.error(f"❌ Content not HTML for {url}: {content_type}")
            return []

        self.already_crawled.add(url)

        # Get config for this URL
        config = self.find_config_for_url(url)
        target_content = config.get("target_content", ["body"])
        ignore_selectors = config.get("ignore_selectors", [])
        # Parse HTML
        soup = BeautifulSoup(response.text, "html.parser")

        # Strip unwanted tags
        for script in soup(["script", "style"]):
            script.decompose()

        # Remove ignored selectors
        for selector in ignore_selectors:
            for element in soup.select(selector):
                element.decompose()

        # Check if we should process this file
        file_exists = os.path.exists(file_path)
        should_write = self.force_overwrite or not file_exists
        file_name = os.path.basename(file_path)

        if should_write:
            content = ""

            # Get target content
            for target in target_content:
                for tag in soup.select(target):
                    content += str(tag)

            if content:
                if self.file_extension.lower() in [".md", ".markdown"]:
                    # Create our custom converter
                    converter = BetterConverter(
                        heading_style="ATX",
                        bullets="-",
                        code_language_callback=self._get_code_language,
                        pulumi_language=config.get("pulumi_language", None),
                    )

                    output = converter.convert(content)
                    output = self.format_markdown(output)
                else:
                    # Otherwise keep as HTML
                    output = content

                action = "Updated" if file_exists else "Created"
                logger.info(
                    f"{action} 📝 {file_name} ({config.get('description', 'unknown config')})"
                )

                # Write content to file
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(output)
            else:
                logger.warning(
                    f"❌ Empty content for {file_path}. Check your target_content selectors."
                )
        else:
            logger.debug(f"Skipped writing file (already exists): {file_name}")

        # Get child URLs
        child_urls = []
        for link in soup.find_all("a"):
            href = link.get("href")
            if not href:
                continue

            # Skip fragment links and javascript links
            if href.startswith("#") or href.startswith("javascript:"):
                continue

            # Handle relative URLs properly
            if not href.startswith(("http://", "https://")):
                # First ensure base URL ends with slash for proper relative path resolution
                base_url = url if url.endswith("/") else url + "/"

                # Now use urljoin which will correctly handle the relative path
                full_url = urllib.parse.urljoin(base_url, href)

                logger.debug(f"🔍 RELATIVE LINK FOUND: '{href}' on page '{url}'")
                logger.debug(f"🔄 RELATIVE LINK RESOLVED: '{href}' → '{full_url}'")
            else:
                full_url = href

            normalized_url = self.normalize_url(full_url)

            # Check if this URL should be crawled
            if normalized_url not in self.already_crawled and self.should_crawl_url(
                normalized_url
            ):
                child_urls.append(normalized_url)
                logger.debug(f"✅ ADDING TO QUEUE: {normalized_url}")

        # Limit the number of child URLs if specified
        if self.max_children_per_page and len(child_urls) > self.max_children_per_page:
            logger.debug(
                f"Limiting child URLs from {len(child_urls)} to {self.max_children_per_page}"
            )
            child_urls = child_urls[: self.max_children_per_page]

        return list(set(child_urls))  # Remove duplicates

    def generate_file_path(self, url):
        """Generate an appropriate file path for a URL"""
        parsed_url = urllib.parse.urlparse(url)
        domain = parsed_url.netloc.replace("www.", "")

        # Create domain subdirectory for external URLs
        base_dir = self.output_dir
        if parsed_url.netloc != self.base_domain:
            base_dir = os.path.join(self.output_dir, domain)
            os.makedirs(base_dir, exist_ok=True)

        # Extract path components
        path_parts = parsed_url.path.strip("/").split("/")

        # Handle empty path
        if not path_parts or all(not part for part in path_parts):
            file_name = "index"
        else:
            # Use the last non-empty part as the base filename
            file_name = next((part for part in reversed(path_parts) if part), "index")

        # Clean filename and ensure it's valid
        file_name = re.sub(r"[^a-zA-Z0-9_-]", "-", file_name)

        # Create directories for nested paths if needed
        if len(path_parts) > 1 and all(path_parts):
            # Create nested directory structure
            nested_dirs = os.path.join(base_dir, *path_parts[:-1])
            os.makedirs(nested_dirs, exist_ok=True)
            return os.path.join(nested_dirs, file_name + self.file_extension)

        return os.path.join(base_dir, file_name + self.file_extension)

    def worker(self, q):
        """Worker thread function"""
        while not q.empty():
            try:
                depth, url = q.get(timeout=1)  # Add timeout to avoid hanging
            except queue.Empty:
                break

            if depth > self.max_depth:
                q.task_done()
                continue

            # Generate file path for the URL
            file_path = self.generate_file_path(url)

            # Crawl the URL and get child URLs
            child_urls = self.crawl_url(url, file_path)

            for child_url in child_urls:
                q.put((depth + 1, child_url))

            q.task_done()
            time.sleep(self.throttle)  # Be nice to the server

    def run(self):
        """Start the crawling process"""
        logger.info(f"Starting crawl at {self.base_url}")
        logger.info(f"Output directory: {self.output_dir}")

        if self.same_domain_only:
            logger.info(f"Restricting to domain: {self.base_domain}")
        if self.max_children_per_page:
            logger.info(f"Limiting to {self.max_children_per_page} children per page")

        # Create a queue of URLs to crawl
        q = queue.Queue()
        q.put((0, self.base_url))

        # Start worker threads
        threads = []
        for i in range(self.num_threads):
            t = threading.Thread(target=self.worker, args=(q,))
            threads.append(t)
            t.start()
            logger.debug(f"Started thread {i+1} of {self.num_threads}")

        # Wait for all threads to finish
        for t in threads:
            t.join()

        logger.info("🏁 All threads have finished")
        logger.info(f"Total pages crawled: {len(self.already_crawled)}")
        return len(self.already_crawled)
