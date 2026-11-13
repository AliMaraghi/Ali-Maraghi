"""Contract tests with synthetic fixtures for the PubMed, YouTube and Starling read adapters. No network."""
import json
import os
import stat
import tempfile
import unittest

from apex import pubmed, starling, youtube_stats

TOKEN = "t" * 40
UID = "11111111-2222-3333-4444-555555555555"
CAT = "66666666-7777-8888-9999-000000000000"
ITEM = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


class Fake:
    def __init__(self, body, status=200, ctype="application/json", raises=None):
        self.body, self.status, self.ctype, self.raises, self.calls = body, status, ctype, raises, []

    def __call__(self, method, path, headers, *rest):
        self.calls.append((method, path, headers))
        if self.raises:
            raise self.raises
        raw = self.body if isinstance(self.body, bytes) else json.dumps(self.body).encode()
        return self.status, self.ctype, raw


class NoWait:
    def wait(self):
        pass


XML = b"""<?xml version="1.0"?><PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>12345</PMID>
<DateRevised><Year>2024</Year><Month>03</Month><Day>05</Day></DateRevised>
<Article><Journal><JournalIssue><PubDate><Year>2020</Year><Month>Jan</Month></PubDate></JournalIssue></Journal>
<ArticleTitle>A <i>synthetic</i> title</ArticleTitle><Abstract><AbstractText Label="BACKGROUND">Background text.</AbstractText>
<AbstractText Label="RESULTS">Result text.</AbstractText></Abstract><ArticleDate DateType="Electronic"><Year>2019</Year><Month>12</Month><Day>30</Day></ArticleDate>
<PublicationTypeList><PublicationType UI="D016441">Retracted Publication</PublicationType></PublicationTypeList></Article>
<CommentsCorrectionsList><CommentsCorrections RefType="RetractionIn"><PMID>67890</PMID></CommentsCorrections></CommentsCorrectionsList>
</MedlineCitation></PubmedArticle></PubmedArticleSet>"""


class PubMedTests(unittest.TestCase):
    def test_search_path_shape_and_validation(self):
        path = pubmed.build_search_path("covid vaccine", retmax=50, sort="pub_date", mindate="2020/01", maxdate="2021/01/31", usehistory=True)
        for part in ("db=pubmed", "retmode=json", "retmax=50", "sort=pub_date", "datetype=pdat", "usehistory=y", "tool=apex-research"):
            self.assertIn(part, path)
        self.assertNotIn("email=", path)
        for bad in ({"sort": "random"}, {"retmax": 10001}, {"mindate": "2020"}, {"api_key": "short"}, {"email": "not-an-email"}):
            with self.assertRaises(ValueError):
                pubmed.build_search_path("x", **bad)
        with self.assertRaises(ValueError):
            pubmed.build_search_path("bad\x00term")

    def test_fetch_path_ids_or_history_not_both(self):
        self.assertIn("id=1%2C2", pubmed.build_fetch_path(["1", "2"]))
        history = pubmed.build_fetch_path(webenv="MCID_abcdef123456", query_key="1", retstart=0, retmax=20)
        self.assertIn("WebEnv=MCID_abcdef123456", history)
        with self.assertRaises(ValueError):
            pubmed.build_fetch_path(["1"], webenv="MCID_abcdef123456", query_key="1")
        with self.assertRaises(ValueError):
            pubmed.build_fetch_path(["01"])

    def test_search_parses_and_fails_closed(self):
        body = {"esearchresult": {"count": "2", "retmax": "2", "idlist": ["123", "456"], "webenv": "MCID_abcdef123456", "querykey": "1"}}
        out = pubmed.search("term", Fake(body), NoWait(), usehistory=True)
        self.assertEqual((out["count"], out["pmids"], out["query_key"]), (2, ["123", "456"], "1"))
        for broken in ({"esearchresult": {"count": "x", "idlist": []}}, {"nope": 1}, {"esearchresult": {"count": "1", "idlist": ["abc"]}}):
            with self.assertRaisesRegex(pubmed.PubMedError, "INVALID_RESPONSE"):
                pubmed.search("term", Fake(broken), NoWait())
        with self.assertRaisesRegex(pubmed.PubMedError, "PUBMED_HTTP_429"):
            pubmed.search("term", Fake({}, status=429), NoWait())

    def test_transport_error_never_leaks_api_key(self):
        key = "A" * 32
        with self.assertRaises(pubmed.PubMedError) as ctx:
            pubmed.search("term", Fake({}, raises=RuntimeError("https://x?api_key=" + key)), NoWait(), api_key=key)
        self.assertNotIn(key, str(ctx.exception))

    def test_efetch_parsing_retraction_and_untrusted_text(self):
        out = pubmed.fetch_records("2026-11-12", Fake(XML, ctype="text/xml"), NoWait(), pmids=["12345", "99999"])
        record = out["records"][0]
        self.assertEqual(record["pmid"], "12345")
        self.assertEqual(record["title"]["role"], "data")
        self.assertIn("synthetic", record["title"]["content"])
        self.assertIn("BACKGROUND: Background text.", record["abstract"]["content"])
        self.assertTrue(record["retraction"]["retracted_publication_type"])
        self.assertEqual(record["retraction"]["retraction_in"], ["67890"])
        self.assertEqual(record["pub_date"], "2020-Jan")
        self.assertEqual(out["missing_pmids"], ["99999"])
        with self.assertRaises(pubmed.PubMedError):
            pubmed.parse_efetch_xml(b"<!DOCTYPE x [<!ENTITY a 'b'>]><x/>", "2026-11-12")

    def test_rate_limiter_spaces_requests(self):
        now, slept = [0.0], []
        limiter = pubmed.RateLimiter(clock=lambda: now[0], sleep=lambda s: (slept.append(s), now.__setitem__(0, now[0] + s)), interval=0.34)
        limiter.wait()
        now[0] += 0.1
        limiter.wait()
        self.assertAlmostEqual(slept[0], 0.24, places=2)
        self.assertEqual(pubmed.limiter_for("K" * 24).interval, pubmed.MIN_INTERVAL_KEYED)


class YouTubeTests(unittest.TestCase):
    def channel(self, **stats):
        base = {"viewCount": "1000", "subscriberCount": "1500", "hiddenSubscriberCount": False, "videoCount": "12"}
        base.update(stats)
        return {"items": [{"id": "UCabcdefghij1234", "statistics": base}]}

    def test_snapshot_rows_and_request_shape(self):
        fake = Fake(self.channel())
        rows = youtube_stats.fetch_channel_snapshots(TOKEN, "2026-11-12", fake)
        self.assertEqual(rows[0]["metrics"], {"views": 1000, "posts": 12, "followers": 1500})
        self.assertEqual(rows[0]["platform"], "youtube")
        method, path, headers = fake.calls[0]
        self.assertEqual((method, path), ("GET", youtube_stats.PATH))
        self.assertEqual(headers["Authorization"], "Bearer " + TOKEN)

    def test_hidden_subscribers_and_integer_counts(self):
        rows = youtube_stats.fetch_channel_snapshots(TOKEN, "2026-11-12", Fake(self.channel(hiddenSubscriberCount=True, viewCount=5)))
        self.assertNotIn("followers", rows[0]["metrics"])
        self.assertEqual(rows[0]["metrics"]["views"], 5)

    def test_errors_and_not_configured(self):
        with self.assertRaisesRegex(youtube_stats.YouTubeError, "NOT_CONFIGURED"):
            youtube_stats.fetch_channel_snapshots(None, "2026-11-12", Fake({}))
        with self.assertRaisesRegex(youtube_stats.YouTubeError, "YOUTUBE_HTTP_403"):
            youtube_stats.fetch_channel_snapshots(TOKEN, "2026-11-12", Fake({}, status=403))
        paged = dict(self.channel(), nextPageToken="x")
        with self.assertRaisesRegex(youtube_stats.YouTubeError, "PAGE_LIMIT_REACHED"):
            youtube_stats.fetch_channel_snapshots(TOKEN, "2026-11-12", Fake(paged))
        with self.assertRaisesRegex(youtube_stats.YouTubeError, "INVALID_RESPONSE"):
            youtube_stats.fetch_channel_snapshots(TOKEN, "2026-11-12", Fake(self.channel(viewCount="-1")))

    def test_scope_policy(self):
        self.assertTrue(youtube_stats.assert_scopes([youtube_stats.READONLY]))
        for bad in (["https://www.googleapis.com/auth/youtube.upload", youtube_stats.READONLY], ["https://www.googleapis.com/auth/youtube"]):
            with self.assertRaises(youtube_stats.YouTubeError):
                youtube_stats.assert_scopes(bad)
        with self.assertRaisesRegex(youtube_stats.YouTubeError, "MISSING_READONLY_SCOPE"):
            youtube_stats.assert_scopes(["openid"])


class StarlingTests(unittest.TestCase):
    def test_accounts_balance_and_get_only(self):
        fake = Fake({"accounts": [{"accountUid": UID, "defaultCategory": CAT, "currency": "GBP"}]})
        accounts = starling.list_accounts(TOKEN, fake)
        self.assertEqual(accounts[0], {"account_uid": UID, "default_category": CAT, "currency": "GBP"})
        self.assertEqual(fake.calls[0][:2], ("GET", "/api/v2/accounts"))
        bal = starling.get_balance(TOKEN, UID, Fake({"clearedBalance": {"currency": "GBP", "minorUnits": 12345}}))
        self.assertEqual(bal["cleared"], {"minor": 12345, "currency": "GBP"})
        self.assertIsNone(bal["effective"])
        for op in ("payment", "transfer", "payees"):
            with self.assertRaises(ValueError):
                starling.request(op, TOKEN, Fake({}))
        self.assertEqual(starling.READ_ONLY_OPERATIONS, frozenset({"accounts", "balance", "feed_changes"}))

    def test_integer_minor_units_enforced(self):
        with self.assertRaisesRegex(starling.StarlingError, "INVALID_RESPONSE"):
            starling.get_balance(TOKEN, UID, Fake({"clearedBalance": {"currency": "GBP", "minorUnits": 12.5}}))

    def feed(self, status="PENDING", direction="OUT", amount=250, updated="2026-11-10T10:00:00.000Z"):
        return {"feedItems": [{"feedItemUid": ITEM, "amount": {"currency": "GBP", "minorUnits": amount}, "direction": direction, "status": status,
                               "transactionTime": "2026-11-10T09:00:00.000Z", "updatedAt": updated, "counterPartyName": "Shop"}]}

    def test_feed_incremental_cursor_and_upsert(self):
        fake = Fake(self.feed())
        out = starling.fetch_feed_changes(TOKEN, UID, CAT, fake, "2026-11-01T00:00:00.000Z")
        item = out["items"][0]
        self.assertEqual((item["minor"], item["status"], item["reference"]), (-250, "PDNG", f"{UID}/{ITEM}"))
        self.assertIn("changesSince=2026-11-01T00%3A00%3A00.000Z", fake.calls[0][1])
        self.assertEqual(out["next_cursor"], "2026-11-10T09:55:00.000Z")        # newest updatedAt minus 300 s
        first = starling.upsert_items({}, out["items"])
        later = starling.fetch_feed_changes(TOKEN, UID, CAT, Fake(self.feed(status="SETTLED")), out["next_cursor"])
        second = starling.upsert_items(first["merged"], later["items"])
        self.assertEqual(second["changed"], [f"{UID}/{ITEM}"])
        self.assertEqual(second["merged"][f"{UID}/{ITEM}"]["status"], "BOOK")
        self.assertEqual(first["merged"][f"{UID}/{ITEM}"]["status"], "PDNG")        # input not mutated
        empty = starling.fetch_feed_changes(TOKEN, UID, CAT, Fake({"feedItems": []}), out["next_cursor"])
        self.assertEqual(empty["next_cursor"], out["next_cursor"])

    def test_unknown_status_and_errors_fail_closed(self):
        with self.assertRaisesRegex(starling.StarlingError, "INVALID_RESPONSE"):
            starling.fetch_feed_changes(TOKEN, UID, CAT, Fake(self.feed(status="REVERSED")), "2026-11-01T00:00:00.000Z")
        with self.assertRaisesRegex(starling.StarlingError, "STARLING_HTTP_401"):
            starling.list_accounts(TOKEN, Fake({}, status=401))
        with self.assertRaisesRegex(starling.StarlingError, "NOT_CONFIGURED"):
            starling.list_accounts(None, Fake({}))

    def test_token_file_rules_and_redaction(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "token")
            with self.assertRaisesRegex(starling.StarlingError, "NOT_CONFIGURED"):
                starling.load_token(path)
            with open(path, "w") as f:
                f.write(TOKEN + "\n")
            os.chmod(path, 0o644)
            with self.assertRaises(ValueError):
                starling.load_token(path)
            os.chmod(path, 0o600)
            self.assertEqual(starling.load_token(path), TOKEN)
        text = starling.redact("Authorization: Bearer " + TOKEN + " and " + "Z" * 30)
        self.assertNotIn(TOKEN, text)
        self.assertNotIn("Z" * 30, text)


if __name__ == "__main__":
    unittest.main()
