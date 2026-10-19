import responses

from biblio_search.query.model import Or, Term
from biblio_search.sources import arxiv, crossref, pubmed, scopus

NODE = Or((Term("deep learning"), Term("radiology")))

SCOPUS_ENTRY = {
    "eid": "2-s2.0-1",
    "dc:title": "Deep learning in radiology",
    "prism:doi": "10.1/ABC",
    "prism:publicationName": "Radiology",
    "prism:coverDate": "2021-05-01",
    "dc:description": "Abstract text",
    "subtypeDescription": "Article",
    "author": [{"surname": "Smith", "given-name": "Jane"}],
    "link": [{"@ref": "scopus", "@href": "https://scopus/1"}],
}


@responses.activate
def test_scopus_search_and_parse(settings) -> None:
    responses.get(
        scopus.URL,
        json={
            "search-results": {"opensearch:totalResults": "1", "entry": [SCOPUS_ENTRY]}
        },
    )
    result = scopus.ScopusSource(settings).search(NODE, (None, None), 10)
    r = result.records[0]
    assert (r.title, r.doi, r.year, r.authors) == (
        "Deep learning in radiology",
        "10.1/abc",
        2021,
        ["Smith, Jane"],
    )
    assert responses.calls[0].request.headers["X-ELS-APIKey"] == "KEY"
    assert result.total_reported == 1


@responses.activate
def test_scopus_falls_back_to_standard_view(settings) -> None:
    responses.get(scopus.URL, status=401, body="not authorized for view COMPLETE")
    responses.get(
        scopus.URL,
        json={
            "search-results": {
                "opensearch:totalResults": "0",
                "entry": [{"error": "Result set was empty"}],
            }
        },
    )
    result = scopus.ScopusSource(settings).search(NODE, (None, None), 10)
    assert result.params["view"] == "STANDARD"
    assert result.records == [] and "STANDARD" in result.warnings[0]


PUBMED_XML = """<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>123</PMID>
<Article><Journal><JournalIssue><PubDate><Year>2022</Year></PubDate></JournalIssue>
<Title>J Radiol</Title></Journal><ArticleTitle>Deep learning for <i>CT</i></ArticleTitle>
<Abstract><AbstractText Label="BACKGROUND">Bg.</AbstractText><AbstractText Label="RESULTS">Res.</AbstractText></Abstract>
<AuthorList><Author><LastName>Pérez</LastName><ForeName>Ana</ForeName></Author>
<Author><CollectiveName>The Group</CollectiveName></Author></AuthorList>
<PublicationTypeList><PublicationType>Journal Article</PublicationType></PublicationTypeList>
</Article></MedlineCitation><PubmedData><ArticleIdList><ArticleId IdType="doi">10.2/XYZ</ArticleId>
</ArticleIdList></PubmedData></PubmedArticle></PubmedArticleSet>"""


@responses.activate
def test_pubmed_esearch_efetch(settings) -> None:
    responses.get(
        pubmed.BASE + "esearch.fcgi",
        json={
            "esearchresult": {"count": "1", "idlist": ["123"], "querytranslation": "QT"}
        },
    )
    responses.post(pubmed.BASE + "efetch.fcgi", body=PUBMED_XML)
    result = pubmed.PubMedSource(settings).search(NODE, (2020, None), 10)
    r = result.records[0]
    assert r.title == "Deep learning for CT"
    assert r.authors == ["Pérez, Ana", "The Group"]
    assert r.abstract == "BACKGROUND: Bg.\nRESULTS: Res."
    assert (r.doi, r.year, r.source_id) == ("10.2/xyz", 2022, "123")
    assert result.params["querytranslation"] == "QT"
    sent = responses.calls[0].request.url
    assert "mindate=2020" in sent and "email=test%40example.org" in sent


@responses.activate
def test_crossref_filters_locally(settings) -> None:
    items = [
        {
            "DOI": "10.3/a",
            "title": ["Deep learning tools"],
            "issued": {"date-parts": [[2020]]},
        },
        {
            "DOI": "10.3/b",
            "title": ["Cardiology outcomes"],
            "issued": {"date-parts": [[2020]]},
        },
    ]
    responses.get(
        crossref.URL,
        json={"message": {"items": items, "total-results": 2, "next-cursor": "c2"}},
    )
    responses.get(crossref.URL, json={"message": {"items": [], "total-results": 2}})
    result = crossref.CrossrefSource(settings).search(NODE, (2020, 2021), 10)
    assert [r.doi for r in result.records] == ["10.3/a"]
    assert (
        "filter=from-pub-date%3A2020%2Cuntil-pub-date%3A2021"
        in responses.calls[0].request.url
    )
    assert "revisaron las primeras 2" in result.warnings[-1]


ARXIV_XML = """<feed xmlns="http://www.w3.org/2005/Atom"
 xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/"
 xmlns:arxiv="http://arxiv.org/schemas/atom">
<opensearch:totalResults>1</opensearch:totalResults>
<entry><id>http://arxiv.org/abs/2101.00001v2</id><published>2021-01-01T00:00:00Z</published>
<title>Deep
 learning</title><summary>Sum.</summary>
<author><name>Kaiming He</name></author>
<arxiv:primary_category term="cs.CV"/></entry></feed>"""


@responses.activate
def test_arxiv_atom(settings) -> None:
    responses.get(arxiv.URL, body=ARXIV_XML)
    result = arxiv.ArxivSource(settings).search(NODE, (None, None), 10)
    r = result.records[0]
    assert (r.source_id, r.title, r.authors) == (
        "2101.00001",
        "Deep learning",
        ["He, Kaiming"],
    )
    assert r.doi == "10.48550/arxiv.2101.00001"
