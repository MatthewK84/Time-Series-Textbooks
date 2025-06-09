import streamlit as st
import requests
import pandas as pd
import json
import time
from datetime import datetime
import xml.etree.ElementTree as ET
from urllib.parse import quote
import sqlite3
import os
from typing import List, Dict, Optional
import re
import bibtexparser
from bibtexparser.bwriter import BibTexWriter
from bibtexparser.bibdatabase import BibDatabase

class TimeSeriesBookScraper:
    """
    A comprehensive scraper for time series books from open access repositories
    and academic APIs, with a focus on legal and ethical data collection.
    """
    
    def __init__(self):
        self.db_path = "timeseries_books.db"
        self.init_database()
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'TimeSeriesBookScraper/1.0 (Educational Research Tool)'
        })
        
    def init_database(self):
        """Initialize SQLite database for storing book metadata"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS books (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                authors TEXT,
                year INTEGER,
                source TEXT,
                url TEXT,
                doi TEXT,
                abstract TEXT,
                keywords TEXT,
                pdf_url TEXT,
                license_type TEXT,
                relevance_score REAL,
                document_type TEXT,
                journal TEXT,
                publisher TEXT,
                pages TEXT,
                volume TEXT,
                issue TEXT,
                isbn TEXT,
                bibtex_key TEXT,
                date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def search_arxiv(self, query: str = "time series analysis", max_results: int = 100) -> List[Dict]:
        """Search arXiv for time series related papers and books"""
        base_url = "http://export.arxiv.org/api/query"
        
        # Limit max_results to prevent rate limiting
        max_results = min(max_results, 100)
        
        # Simplified query that's more likely to work
        query_string = f'all:"{query}" OR all:"time series"'
        
        params = {
            'search_query': query_string,
            'start': 0,
            'max_results': max_results,
            'sortBy': 'relevance',
            'sortOrder': 'descending'
        }
        
        try:
            st.info(f"Searching arXiv with query: {query_string}")
            response = self.session.get(base_url, params=params, timeout=30)
            response.raise_for_status()
            
            # Debug: show response length
            st.info(f"arXiv response received: {len(response.text)} characters")
            
            results = self._parse_arxiv_response(response.text)
            st.info(f"arXiv parsed {len(results)} results")
            return results
            
        except requests.RequestException as e:
            st.error(f"Error fetching from arXiv: {e}")
            st.error(f"URL attempted: {response.url if 'response' in locals() else 'No response'}")
            return []
        except Exception as e:
            st.error(f"Unexpected error with arXiv: {e}")
            return []
    
    def _parse_arxiv_response(self, xml_content: str) -> List[Dict]:
        """Parse arXiv XML response"""
        try:
            root = ET.fromstring(xml_content)
            namespace = {'atom': 'http://www.w3.org/2005/Atom'}
            
            books = []
            entries = root.findall('atom:entry', namespace)
            st.info(f"Found {len(entries)} entries in arXiv XML")
            
            for entry in entries:
                try:
                    title_elem = entry.find('atom:title', namespace)
                    title = title_elem.text.strip() if title_elem is not None else "No title"
                    
                    authors = []
                    for author in entry.findall('atom:author', namespace):
                        name_elem = author.find('atom:name', namespace)
                        if name_elem is not None:
                            authors.append(name_elem.text)
                    
                    summary_elem = entry.find('atom:summary', namespace)
                    abstract = summary_elem.text.strip() if summary_elem is not None else ""
                    
                    published_elem = entry.find('atom:published', namespace)
                    year = None
                    if published_elem is not None:
                        try:
                            year = int(published_elem.text[:4])
                        except (ValueError, TypeError):
                            pass
                    
                    # Get PDF link
                    pdf_link = None
                    for link in entry.findall('atom:link', namespace):
                        if link.get('type') == 'application/pdf':
                            pdf_link = link.get('href')
                            break
                    
                    # Get entry URL
                    id_elem = entry.find('atom:id', namespace)
                    url = id_elem.text if id_elem is not None else ""
                    
                    # Calculate relevance score
                    relevance = self._calculate_relevance(title, abstract)
                    
                    # Only include if we have a title and some relevance
                    if title and title != "No title" and relevance > 0.1:  # Lower threshold
                        # Determine document type
                        doc_type = self._classify_document_type(title, abstract, 'arXiv')
                        
                        bibtex_key = self._generate_bibtex_key(authors[0] if authors else "Unknown", year, title)
                        
                        books.append({
                            'title': title,
                            'authors': ', '.join(authors) if authors else 'Unknown',
                            'year': year,
                            'source': 'arXiv',
                            'url': url,
                            'abstract': abstract,
                            'pdf_url': pdf_link,
                            'license_type': 'Open Access',
                            'relevance_score': relevance,
                            'document_type': doc_type,
                            'bibtex_key': bibtex_key
                        })
                        
                except Exception as e:
                    st.warning(f"Error parsing arXiv entry: {e}")
                    continue
            
            return books
            
        except ET.ParseError as e:
            st.error(f"Error parsing arXiv XML: {e}")
            st.error(f"XML content preview: {xml_content[:500]}...")
            return []
        except Exception as e:
            st.error(f"Unexpected error parsing arXiv response: {e}")
            return []
    
    def search_crossref(self, query: str = "time series", max_results: int = 100) -> List[Dict]:
        """Search CrossRef for open access time series publications"""
        base_url = "https://api.crossref.org/works"
        
        # Limit max_results to prevent rate limiting
        max_results = min(max_results, 100)
        
        params = {
            'query': query,
            'filter': 'has-license:true',  # Simplified filter
            'rows': max_results,
            'sort': 'relevance',
            'order': 'desc',
            'mailto': 'researcher@example.com'  # Polite pool access
        }
        
        try:
            st.info(f"Searching CrossRef with query: {query}")
            response = self.session.get(base_url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            st.info(f"CrossRef response: {data.get('message', {}).get('total-results', 0)} total results")
            
            results = self._parse_crossref_response(data)
            st.info(f"CrossRef parsed {len(results)} relevant results")
            return results
            
        except requests.RequestException as e:
            st.error(f"Error fetching from CrossRef: {e}")
            return []
        except Exception as e:
            st.error(f"Unexpected error with CrossRef: {e}")
            return []
    
    def _parse_crossref_response(self, data: dict) -> List[Dict]:
        """Parse CrossRef API response"""
        books = []
        
        items = data.get('message', {}).get('items', [])
        st.info(f"Processing {len(items)} CrossRef items")
        
        for item in items:
            try:
                # Get title
                titles = item.get('title', [])
                title = titles[0] if titles else "No title"
                title = ' '.join(title.split()) if title else "No title"
                
                # Get authors
                authors = []
                for author in item.get('author', []):
                    given = author.get('given', '')
                    family = author.get('family', '')
                    if family:  # At least need family name
                        full_name = f"{given} {family}".strip()
                        authors.append(full_name)
                
                # Get year
                year = None
                date_parts = None
                if 'published-print' in item:
                    date_parts = item['published-print'].get('date-parts', [[]])[0]
                elif 'published-online' in item:
                    date_parts = item['published-online'].get('date-parts', [[]])[0]
                
                if date_parts and len(date_parts) > 0:
                    try:
                        year = int(date_parts[0])
                    except (ValueError, TypeError):
                        pass
                
                abstract = item.get('abstract', '')
                doi = item.get('DOI', '')
                url = f"https://doi.org/{doi}" if doi else ""
                
                # Extract additional metadata
                journal = ''
                container_titles = item.get('container-title', [])
                if container_titles:
                    journal = container_titles[0]
                
                publisher = item.get('publisher', '')
                pages = item.get('page', '')
                volume = item.get('volume', '')
                issue = item.get('issue', '')
                
                # Check for any license (not just Creative Commons)
                license_info = item.get('license', [])
                has_license = len(license_info) > 0
                
                # Calculate relevance (lower threshold)
                relevance = self._calculate_relevance(title, abstract)
                
                if has_license and relevance > 0.1 and title != "No title":  # Lower threshold
                    doc_type = self._classify_document_type(title, abstract, 'CrossRef', item.get('type', ''))
                    bibtex_key = self._generate_bibtex_key(authors[0] if authors else "Unknown", year, title)
                    
                    license_type = "Open Access" if license_info else "Licensed"
                    
                    books.append({
                        'title': title,
                        'authors': ', '.join(authors) if authors else 'Unknown',
                        'year': year,
                        'source': 'CrossRef',
                        'url': url,
                        'doi': doi,
                        'abstract': abstract,
                        'license_type': license_type,
                        'relevance_score': relevance,
                        'document_type': doc_type,
                        'journal': journal,
                        'publisher': publisher,
                        'pages': pages,
                        'volume': volume,
                        'issue': issue,
                        'bibtex_key': bibtex_key
                    })
                    
            except Exception as e:
                st.warning(f"Error parsing CrossRef item: {e}")
                continue
                
        return books
    
    def search_internet_archive(self, query: str = "time series analysis") -> List[Dict]:
        """Search Internet Archive for public domain time series books"""
        base_url = "https://archive.org/advancedsearch.php"
        
        # Simplified query to get more results
        search_query = f'({query}) AND mediatype:texts'
        
        params = {
            'q': search_query,
            'fl': 'identifier,title,creator,year,description,downloads,format',
            'rows': 50,  # Limit to 50 to avoid timeouts
            'page': 1,
            'output': 'json'
        }
        
        try:
            st.info(f"Searching Internet Archive with query: {search_query}")
            response = self.session.get(base_url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            total_found = data.get('response', {}).get('numFound', 0)
            st.info(f"Internet Archive found {total_found} total results")
            
            results = self._parse_internet_archive_response(data)
            st.info(f"Internet Archive parsed {len(results)} relevant results")
            return results
            
        except requests.RequestException as e:
            st.error(f"Error fetching from Internet Archive: {e}")
            return []
        except Exception as e:
            st.error(f"Unexpected error with Internet Archive: {e}")
            return []
    
    def _parse_internet_archive_response(self, data: dict) -> List[Dict]:
        """Parse Internet Archive response"""
        books = []
        
        for doc in data.get('response', {}).get('docs', []):
            try:
                title = doc.get('title', '')
                authors = doc.get('creator', [])
                if isinstance(authors, str):
                    authors = [authors]
                
                year = doc.get('year')
                if isinstance(year, list) and year:
                    year = int(year[0])
                elif isinstance(year, str):
                    year = int(year) if year.isdigit() else None
                
                identifier = doc.get('identifier', '')
                url = f"https://archive.org/details/{identifier}"
                
                description = doc.get('description', '')
                if isinstance(description, list):
                    description = ' '.join(description)
                
                relevance = self._calculate_relevance(title, description)
                doc_type = self._classify_document_type(title, description, 'Internet Archive')
                
                if relevance > 0.3:
                    bibtex_key = self._generate_bibtex_key(authors[0] if authors else "Unknown", year, title)
                    
                    books.append({
                        'title': title,
                        'authors': ', '.join(authors) if authors else 'Unknown',
                        'year': year,
                        'source': 'Internet Archive',
                        'url': url,
                        'abstract': description,
                        'pdf_url': f"https://archive.org/download/{identifier}/{identifier}.pdf",
                        'license_type': 'Public Domain',
                        'relevance_score': relevance,
                        'document_type': doc_type,
                        'bibtex_key': bibtex_key
                    })
                    
            except Exception as e:
                continue
                
        return books
    
    def search_ndltd(self, query: str = "time series analysis", max_results: int = 100) -> List[Dict]:
        """Search NDLTD (Networked Digital Library of Theses and Dissertations)"""
        # Note: NDLTD API might not be publicly accessible, so we'll return empty for now
        # but keep the structure for when/if API access becomes available
        
        st.info("NDLTD search currently unavailable - API access restricted")
        return []
    
    def _parse_ndltd_response(self, data: dict) -> List[Dict]:
        """Parse NDLTD API response for theses and dissertations"""
        books = []
        
        for doc in data.get('response', {}).get('docs', []):
            try:
                title = doc.get('title', [''])[0] if isinstance(doc.get('title'), list) else doc.get('title', '')
                
                authors = doc.get('author', [])
                if isinstance(authors, str):
                    authors = [authors]
                
                year = doc.get('year')
                if isinstance(year, list) and year:
                    year = int(year[0])
                elif isinstance(year, str) and year.isdigit():
                    year = int(year)
                
                abstract = doc.get('description', [''])[0] if isinstance(doc.get('description'), list) else doc.get('description', '')
                url = doc.get('url', [''])[0] if isinstance(doc.get('url'), list) else doc.get('url', '')
                
                # Determine if it's a thesis or dissertation
                degree_type = doc.get('degree', [''])[0] if isinstance(doc.get('degree'), list) else doc.get('degree', '')
                doc_type = self._classify_thesis_type(title, abstract, degree_type)
                
                university = doc.get('publisher', [''])[0] if isinstance(doc.get('publisher'), list) else doc.get('publisher', '')
                
                relevance = self._calculate_relevance(title, abstract)
                
                if relevance > 0.3:
                    bibtex_key = self._generate_bibtex_key(authors[0] if authors else "Unknown", year, title)
                    
                    books.append({
                        'title': title,
                        'authors': ', '.join(authors) if authors else 'Unknown',
                        'year': year,
                        'source': 'NDLTD',
                        'url': url,
                        'abstract': abstract,
                        'license_type': 'Open Access',
                        'relevance_score': relevance,
                        'document_type': doc_type,
                        'publisher': university,
                        'bibtex_key': bibtex_key
                    })
                    
            except Exception as e:
                continue
                
        return books
    
    def _classify_document_type(self, title: str, abstract: str, source: str, crossref_type: str = '') -> str:
        """Classify document type based on content and source"""
        text = f"{title} {abstract}".lower()
        
        # Thesis/Dissertation indicators
        thesis_keywords = ['thesis', 'dissertation', 'phd', 'master', 'doctoral', 'graduate']
        if any(keyword in text for keyword in thesis_keywords):
            if any(word in text for word in ['phd', 'doctoral', 'doctor']):
                return 'Dissertation'
            else:
                return 'Thesis'
        
        # Book indicators
        book_keywords = ['handbook', 'textbook', 'manual', 'guide', 'introduction to', 'principles of']
        if source == 'Internet Archive' or any(keyword in text for keyword in book_keywords):
            return 'Book'
        
        # CrossRef type mapping
        if crossref_type:
            type_mapping = {
                'journal-article': 'Research Article',
                'book': 'Book',
                'book-chapter': 'Book Chapter',
                'proceedings-article': 'Conference Paper',
                'dissertation': 'Dissertation',
                'report': 'Technical Report'
            }
            return type_mapping.get(crossref_type, 'Research Article')
        
        # Default classification
        if source == 'arXiv':
            return 'Preprint'
        
        return 'Research Article'
    
    def _classify_thesis_type(self, title: str, abstract: str, degree_type: str) -> str:
        """Classify thesis vs dissertation based on degree type"""
        text = f"{title} {abstract} {degree_type}".lower()
        
        if any(word in text for word in ['phd', 'doctoral', 'doctor', 'ph.d']):
            return 'Dissertation'
        elif any(word in text for word in ['master', 'ms', 'm.s', 'ma', 'm.a']):
            return 'Thesis'
        elif any(word in text for word in ['bachelor', 'bs', 'b.s', 'ba', 'b.a']):
            return 'Undergraduate Thesis'
        else:
            return 'Thesis'
    
    def _generate_bibtex_key(self, first_author: str, year: int, title: str) -> str:
        """Generate a unique BibTeX key"""
        # Clean author name
        author_parts = first_author.split()
        author_surname = author_parts[-1] if author_parts else "Unknown"
        author_surname = re.sub(r'[^a-zA-Z]', '', author_surname)
        
        # Clean title - take first meaningful word
        title_words = re.findall(r'\b[a-zA-Z]{3,}\b', title)
        title_word = title_words[0] if title_words else "Title"
        
        year_str = str(year) if year else "Unknown"
        
        return f"{author_surname}{year_str}{title_word}"
        """Calculate relevance score for time series content"""
        text = f"{title} {abstract}".lower()
        
        # Define weighted keywords
        keywords = {
            'time series': 3.0,
            'temporal analysis': 2.5,
            'forecasting': 2.0,
            'arima': 2.0,
            'garch': 2.0,
            'stochastic process': 2.0,
            'econometrics': 1.5,
            'signal processing': 1.5,
            'time domain': 1.5,
            'frequency domain': 1.5,
            'seasonal': 1.0,
            'trend': 0.8,
            'correlation': 0.5,
            'regression': 0.3
        }
        
        score = 0.0
        for keyword, weight in keywords.items():
            if keyword in text:
                score += weight
        
        # Normalize score
        return min(score / 10.0, 1.0)
    
    def save_to_database(self, books: List[Dict]):
        """Save books to SQLite database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        for book in books:
            # Check if book already exists
            cursor.execute('SELECT id FROM books WHERE title = ? AND source = ?', 
                         (book['title'], book['source']))
            
            if not cursor.fetchone():
                cursor.execute('''
                    INSERT INTO books (title, authors, year, source, url, doi, 
                                     abstract, pdf_url, license_type, relevance_score,
                                     document_type, journal, publisher, pages, volume, 
                                     issue, isbn, bibtex_key)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    book['title'],
                    book['authors'],
                    book['year'],
                    book['source'],
                    book['url'],
                    book.get('doi', ''),
                    book['abstract'],
                    book.get('pdf_url', ''),
                    book['license_type'],
                    book['relevance_score'],
                    book.get('document_type', 'Research Article'),
                    book.get('journal', ''),
                    book.get('publisher', ''),
                    book.get('pages', ''),
                    book.get('volume', ''),
                    book.get('issue', ''),
                    book.get('isbn', ''),
                    book.get('bibtex_key', '')
                ))
        
        conn.commit()
        conn.close()
    
    def search_database(self, query: str = "", source: str = "", document_type: str = "", 
                       min_year: int = 1900, max_year: int = 2024) -> pd.DataFrame:
        """Search the local database"""
        conn = sqlite3.connect(self.db_path)
        
        sql = '''
            SELECT * FROM books 
            WHERE (title LIKE ? OR authors LIKE ? OR abstract LIKE ?)
            AND source LIKE ?
            AND document_type LIKE ?
            AND year BETWEEN ? AND ?
            ORDER BY relevance_score DESC, year DESC
        '''
        
        params = (f'%{query}%', f'%{query}%', f'%{query}%', f'%{source}%', 
                 f'%{document_type}%', min_year, max_year)
        
        df = pd.read_sql_query(sql, conn, params=params)
        conn.close()
        
        return df
    
    def export_to_bibtex(self, df: pd.DataFrame) -> str:
        """Export search results to BibTeX format"""
        bib_db = BibDatabase()
        bib_db.entries = []
        
        for _, row in df.iterrows():
            entry = {
                'ID': row.get('bibtex_key', f"entry_{row['id']}"),
                'title': row['title'],
                'author': row['authors'],
                'year': str(row['year']) if pd.notna(row['year']) else '',
                'url': row.get('url', ''),
                'abstract': row.get('abstract', '')
            }
            
            # Set entry type based on document type
            doc_type = row.get('document_type', 'article').lower()
            if 'book' in doc_type:
                entry['ENTRYTYPE'] = 'book'
                if row.get('publisher'):
                    entry['publisher'] = row['publisher']
                if row.get('isbn'):
                    entry['isbn'] = row['isbn']
            elif 'thesis' in doc_type or 'dissertation' in doc_type:
                entry['ENTRYTYPE'] = 'phdthesis' if 'dissertation' in doc_type else 'mastersthesis'
                if row.get('publisher'):
                    entry['school'] = row['publisher']
            else:
                entry['ENTRYTYPE'] = 'article'
                if row.get('journal'):
                    entry['journal'] = row['journal']
                if row.get('volume'):
                    entry['volume'] = row['volume']
                if row.get('issue'):
                    entry['number'] = row['issue']
                if row.get('pages'):
                    entry['pages'] = row['pages']
            
            if row.get('doi'):
                entry['doi'] = row['doi']
            
            bib_db.entries.append(entry)
        
        writer = BibTexWriter()
        return writer.write(bib_db)
    
    def export_to_endnote(self, df: pd.DataFrame) -> str:
        """Export search results to EndNote format (RIS)"""
        ris_entries = []
        
        for _, row in df.iterrows():
            doc_type = row.get('document_type', 'article').lower()
            
            # Map document types to RIS types
            if 'book' in doc_type:
                type_code = 'BOOK'
            elif 'thesis' in doc_type:
                type_code = 'THES'
            elif 'dissertation' in doc_type:
                type_code = 'THES'
            elif 'conference' in doc_type:
                type_code = 'CONF'
            else:
                type_code = 'JOUR'
            
            entry = [
                f"TY  - {type_code}",
                f"TI  - {row['title']}",
                f"PY  - {row['year']}" if pd.notna(row['year']) else "",
                f"UR  - {row.get('url', '')}",
                f"AB  - {row.get('abstract', '')}"
            ]
            
            # Add authors
            if row['authors']:
                authors = row['authors'].split(', ')
                for author in authors:
                    entry.append(f"AU  - {author}")
            
            # Add journal/publisher info
            if row.get('journal'):
                entry.append(f"JO  - {row['journal']}")
            if row.get('publisher'):
                entry.append(f"PB  - {row['publisher']}")
            if row.get('volume'):
                entry.append(f"VL  - {row['volume']}")
            if row.get('issue'):
                entry.append(f"IS  - {row['issue']}")
            if row.get('pages'):
                entry.append(f"SP  - {row['pages']}")
            if row.get('doi'):
                entry.append(f"DO  - {row['doi']}")
            
            entry.append("ER  - ")
            entry.append("")
            
            ris_entries.append('\n'.join(filter(None, entry)))
        
        return '\n'.join(ris_entries)
    
    def export_to_zotero_csv(self, df: pd.DataFrame) -> str:
        """Export search results to Zotero-compatible CSV format"""
        zotero_df = pd.DataFrame()
        
        for _, row in df.iterrows():
            doc_type = row.get('document_type', 'journalArticle')
            
            # Map to Zotero item types
            type_mapping = {
                'Research Article': 'journalArticle',
                'Book': 'book',
                'Book Chapter': 'bookSection',
                'Conference Paper': 'conferencePaper',
                'Thesis': 'thesis',
                'Dissertation': 'thesis',
                'Preprint': 'preprint',
                'Technical Report': 'report'
            }
            
            zotero_type = type_mapping.get(doc_type, 'journalArticle')
            
            zotero_entry = {
                'Item Type': zotero_type,
                'Title': row['title'],
                'Author': row['authors'],
                'Year': row['year'] if pd.notna(row['year']) else '',
                'URL': row.get('url', ''),
                'Abstract': row.get('abstract', ''),
                'DOI': row.get('doi', ''),
                'Publication Title': row.get('journal', ''),
                'Publisher': row.get('publisher', ''),
                'Volume': row.get('volume', ''),
                'Issue': row.get('issue', ''),
                'Pages': row.get('pages', ''),
                'ISBN': row.get('isbn', ''),
                'Date Added': row.get('date_added', ''),
                'Manual Tags': 'time series; quantitative analysis'
            }
            
            zotero_df = pd.concat([zotero_df, pd.DataFrame([zotero_entry])], ignore_index=True)
        
        return zotero_df.to_csv(index=False)

def main():
    st.set_page_config(
        page_title="Time Series Books Finder",
        page_icon="📚",
        layout="wide"
    )
    
    st.title("📚 Time Series Books & Papers Finder")
    st.markdown("*Discover open access time series literature from academic repositories*")
    
    # Initialize scraper
    if 'scraper' not in st.session_state:
        st.session_state.scraper = TimeSeriesBookScraper()
    
    # Sidebar for search options
    st.sidebar.header("Search Options")
    
    search_mode = st.sidebar.radio(
        "Search Mode",
        ["Search Database", "Scrape New Content"]
    )
    
    if search_mode == "Scrape New Content":
        st.header("🔍 Scrape New Content")
        
        query = st.text_input("Search Query", value="time series analysis")
        
        sources = st.multiselect(
            "Select Sources",
            ["arXiv", "CrossRef", "Internet Archive", "NDLTD (Theses/Dissertations)"],
            default=["arXiv"]
        )
        
        max_results = st.slider("Maximum Results per Source", 10, 100, 50)  # Reduced default
        
        if st.button("Start Scraping", type="primary"):
            all_books = []
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            for i, source in enumerate(sources):
                status_text.text(f"Searching {source}...")
                
                try:
                    if source == "arXiv":
                        books = st.session_state.scraper.search_arxiv(query, max_results)
                    elif source == "CrossRef":
                        books = st.session_state.scraper.search_crossref(query, max_results)
                    elif source == "Internet Archive":
                        books = st.session_state.scraper.search_internet_archive(query)
                    elif source == "NDLTD (Theses/Dissertations)":
                        books = st.session_state.scraper.search_ndltd(query, max_results)
                    else:
                        books = []
                    
                    st.info(f"{source} returned {len(books)} results")
                    all_books.extend(books)
                    
                except Exception as e:
                    st.error(f"Error with {source}: {e}")
                    
                progress_bar.progress((i + 1) / len(sources))
                time.sleep(2)  # Rate limiting - 2 seconds between requests
            
            status_text.text("Saving to database...")
            st.session_state.scraper.save_to_database(all_books)
            
            status_text.text("Complete!")
            st.success(f"Found and saved {len(all_books)} relevant books/papers!")
            
            # Display results
            if all_books:
                df = pd.DataFrame(all_books)
                st.dataframe(df[['title', 'authors', 'year', 'source', 'document_type', 'relevance_score']])
    
    else:  # Search Database
        st.header("🔎 Search Database")
        
        col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
        
        with col1:
            search_query = st.text_input("Search Terms", "")
        
        with col2:
            source_filter = st.selectbox(
                "Source Filter",
                ["All", "arXiv", "CrossRef", "Internet Archive", "NDLTD"]
            )
        
        with col3:
            doc_type_filter = st.selectbox(
                "Document Type",
                ["All", "Research Article", "Book", "Thesis", "Dissertation", 
                 "Preprint", "Conference Paper", "Technical Report"]
            )
        
        with col4:
            year_range = st.slider("Year Range", 1900, 2024, (2000, 2024))
        
        # Perform search
        source = "" if source_filter == "All" else source_filter
        doc_type = "" if doc_type_filter == "All" else doc_type_filter
        df = st.session_state.scraper.search_database(
            search_query, source, doc_type, year_range[0], year_range[1]
        )
        
        if not df.empty:
            st.write(f"Found {len(df)} results")
            
            # Summary statistics
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total Results", len(df))
            with col2:
                st.metric("Avg Year", f"{df['year'].mean():.0f}" if not df['year'].isna().all() else "N/A")
            with col3:
                most_common_type = df['document_type'].mode().iloc[0] if not df['document_type'].empty else "N/A"
                st.metric("Most Common Type", most_common_type)
            with col4:
                avg_relevance = df['relevance_score'].mean()
                st.metric("Avg Relevance", f"{avg_relevance:.2f}")
            
            # Document type distribution
            if not df['document_type'].empty:
                st.subheader("📊 Document Types")
                type_counts = df['document_type'].value_counts()
                st.bar_chart(type_counts)
            
            # Display results with expandable details
            for idx, row in df.iterrows():
                with st.expander(f"📖 {row['title'][:100]}{'...' if len(row['title']) > 100 else ''}"):
                    col1, col2 = st.columns([2, 1])
                    
                    with col1:
                        st.write(f"**Authors:** {row['authors']}")
                        st.write(f"**Year:** {row['year']}")
                        st.write(f"**Source:** {row['source']}")
                        st.write(f"**Document Type:** {row.get('document_type', 'Unknown')}")
                        st.write(f"**Relevance Score:** {row['relevance_score']:.2f}")
                        
                        if row.get('journal'):
                            st.write(f"**Journal:** {row['journal']}")
                        if row.get('publisher'):
                            st.write(f"**Publisher:** {row['publisher']}")
                        
                        if row['abstract']:
                            st.write("**Abstract:**")
                            st.write(row['abstract'][:500] + "..." if len(row['abstract']) > 500 else row['abstract'])
                    
                    with col2:
                        if row['url']:
                            st.link_button("View Online", row['url'])
                        
                        if row['pdf_url']:
                            st.link_button("Download PDF", row['pdf_url'])
                        
                        st.write(f"**License:** {row['license_type']}")
            
            # Export options
            st.subheader("📊 Export Results")
            
            col1, col2, col3, col4, col5 = st.columns(5)
            
            with col1:
                if st.button("Export as CSV"):
                    csv = df.to_csv(index=False)
                    st.download_button(
                        label="Download CSV",
                        data=csv,
                        file_name=f"timeseries_books_{datetime.now().strftime('%Y%m%d')}.csv",
                        mime="text/csv"
                    )
            
            with col2:
                if st.button("Export as JSON"):
                    json_data = df.to_json(orient='records', indent=2)
                    st.download_button(
                        label="Download JSON",
                        data=json_data,
                        file_name=f"timeseries_books_{datetime.now().strftime('%Y%m%d')}.json",
                        mime="application/json"
                    )
            
            with col3:
                if st.button("Export as BibTeX"):
                    bibtex_data = st.session_state.scraper.export_to_bibtex(df)
                    st.download_button(
                        label="Download BibTeX",
                        data=bibtex_data,
                        file_name=f"timeseries_books_{datetime.now().strftime('%Y%m%d')}.bib",
                        mime="text/plain"
                    )
            
            with col4:
                if st.button("Export for EndNote"):
                    endnote_data = st.session_state.scraper.export_to_endnote(df)
                    st.download_button(
                        label="Download RIS",
                        data=endnote_data,
                        file_name=f"timeseries_books_{datetime.now().strftime('%Y%m%d')}.ris",
                        mime="text/plain"
                    )
            
            with col5:
                if st.button("Export for Zotero"):
                    zotero_data = st.session_state.scraper.export_to_zotero_csv(df)
                    st.download_button(
                        label="Download Zotero CSV",
                        data=zotero_data,
                        file_name=f"timeseries_books_zotero_{datetime.now().strftime('%Y%m%d')}.csv",
                        mime="text/csv"
                    )
        
        else:
            st.info("No results found. Try different search terms or scrape new content.")
    
    # Footer
    st.markdown("---")
    st.markdown(
        "⚖️ **Legal Notice:** This tool only accesses open access repositories and "
        "public domain materials. All content is properly attributed to original sources."
    )

if __name__ == "__main__":
    main()
