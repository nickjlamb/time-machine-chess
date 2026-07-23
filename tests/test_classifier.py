"""Era classifier tests — plumbing only, on the heuristic engines.

The accuracy of the classifier is validated on the Mac with the real models
(scripts/classify_validation.py); here we pin parsing, sampling rules, the
streaming protocol and the math. Never assert on a neural model's opinion —
and the heuristic move distributions are deterministic (pure softmax of
scores, no sampling), which several tests below rely on."""
import json
import os
import sys
from pathlib import Path

os.environ["TMC_FORCE_HEURISTIC"] = "1"

import chess
import yaml
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.app import app, get_engine  # noqa: E402
from backend import classifier  # noqa: E402

client = TestClient(app)
CFG_ERAS = list(yaml.safe_load(
    (Path(__file__).resolve().parent.parent / "config" / "eras.yaml").read_text()
)["eras"])

OPERA_GAME = """[Event "Paris Opera"]
[White "Morphy, Paul"]
[Black "Duke Karl / Count Isouard"]
[Date "1858.11.02"]
[Result "1-0"]

1. e4 e5 2. Nf3 d6 3. d4 Bg4 4. dxe5 Bxf3 5. Qxf3 dxe5 6. Bc4 Nf6 7. Qb3 Qe7
8. Nc3 c6 9. Bg5 b5 10. Nxb5 cxb5 11. Bxb5+ Nbd7 12. O-O-O Rd8 13. Rxd7 Rxd7
14. Rd1 Qe6 15. Bxd7+ Nxd7 16. Qb8+ Nxb8 17. Rd8# 1-0
"""

EVERGREEN_GAME = """[Event "Berlin"]
[White "Anderssen, Adolf"]
[Black "Dufresne, Jean"]
[Date "1852.??.??"]
[Result "1-0"]

1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5 4. b4 Bxb4 5. c3 Ba5 6. d4 exd4 7. O-O d3
8. Qb3 Qf6 9. e5 Qg6 10. Re1 Nge7 11. Ba3 b5 12. Qxb5 Rb8 13. Qa4 Bb6
14. Nbd2 Bb7 15. Ne4 Qf5 16. Bxd3 Qh5 17. Nf6+ gxf6 18. exf6 Rg8 19. Rad1
Qxf3 20. Rxe7+ Nxe7 21. Qxd7+ Kxd7 22. Bf5+ Ke8 23. Bd7+ Kf8 24. Bxe7# 1-0
"""


def test_parse_pgn_games():
    games = classifier.parse_pgn_games(OPERA_GAME + "\n" + EVERGREEN_GAME)
    assert len(games) == 2
    assert games[0].headers["White"].startswith("Morphy")
    assert classifier.parse_pgn_games("not a pgn at all") == []


def test_identify_player():
    games = classifier.parse_pgn_games(OPERA_GAME + "\n" + EVERGREEN_GAME)
    assert classifier.identify_player(games, "Morphy, Paul") == "Morphy, Paul"
    # No repeated name across these two games and none given -> None
    assert classifier.identify_player(games) is None
    # A single anonymous-opponent game claims its White player
    solo = classifier.parse_pgn_games(OPERA_GAME)
    assert classifier.identify_player(solo).startswith("Morphy")


def test_sampling_rules():
    games = classifier.parse_pgn_games(OPERA_GAME)
    positions = classifier.sample_positions(games, "Morphy, Paul")
    assert positions, "should sample something"
    for p in positions:
        assert p["ply"] >= classifier.SKIP_PLIES       # opening skipped
        assert p["ply"] % 2 == 0                        # White (Morphy) to move
        board = chess.Board(p["fen"])
        assert chess.Move.from_uci(p["move"]) in board.legal_moves
        assert len(list(board.legal_moves)) >= classifier.MIN_LEGAL_MOVES
    # Classifying the Black player samples the other color's plies
    black = classifier.sample_positions(games, "Duke Karl / Count Isouard")
    assert black and all(p["ply"] % 2 == 1 for p in black)


def test_sampling_cap_is_even_and_deterministic():
    games = classifier.parse_pgn_games(EVERGREEN_GAME)
    full = classifier.sample_positions(games, "Anderssen, Adolf")
    capped = classifier.sample_positions(games, "Anderssen, Adolf",
                                         max_positions=5)
    assert len(capped) == 5
    assert capped == classifier.sample_positions(games, "Anderssen, Adolf",
                                                 max_positions=5)
    # Even thinning spans the game rather than truncating it
    assert capped[-1]["ply"] > full[len(full) // 2]["ply"]


def test_both_colors_mode():
    games = classifier.parse_pgn_games(OPERA_GAME)
    both = classifier.sample_positions(games, both_colors=True)
    plies = {p["ply"] % 2 for p in both}
    assert plies == {0, 1}


def test_era_mix_math():
    lls = {"a": [-1.0, -1.0], "b": [-2.0, -2.0], "c": [-3.0, -3.0]}
    mix = classifier._era_mix(lls)
    assert abs(sum(mix.values()) - 1.0) < 1e-9
    assert mix["a"] > mix["b"] > mix["c"]


def test_classify_stream_protocol_and_determinism():
    games = classifier.parse_pgn_games(OPERA_GAME + "\n" + EVERGREEN_GAME)
    positions = classifier.sample_positions(games, both_colors=True)

    def run():
        return list(classifier.classify_stream(positions, CFG_ERAS, get_engine))

    events = run()
    assert [e["era"] for e in events if e["type"] == "era_start"] == CFG_ERAS
    result = events[-1]
    assert result["type"] == "result"
    assert set(result["mix"]) == set(CFG_ERAS)
    assert abs(sum(result["mix"].values()) - 100.0) < 0.5
    assert result["topEra"] in CFG_ERAS
    # One characteristic move per era, and it's a legal move of its position
    assert set(result["characteristicMoves"]) == set(CFG_ERAS)
    for cm in result["characteristicMoves"].values():
        board = chess.Board(cm["fen"])
        assert chess.Move.from_uci(cm["move"]) in board.legal_moves
    # Heuristic distributions are deterministic -> identical repeat run
    assert run()[-1]["mix"] == result["mix"]


def test_classify_endpoint_streams_ndjson():
    r = client.post("/api/classify", json={"pgn": OPERA_GAME + "\n" + EVERGREEN_GAME})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/x-ndjson")
    lines = [json.loads(l) for l in r.text.strip().splitlines()]
    assert lines[0]["type"] == "start"
    assert lines[0]["eras"] == CFG_ERAS and lines[0]["games"] == 2
    assert [e["era"] for e in lines if e["type"] == "era_done"] == CFG_ERAS
    result = lines[-1]
    assert result["type"] == "result"
    assert result["games"] == 2 and result["positions"] == lines[0]["positions"]
    assert result["verdict"]  # top era's verdict line, from config


def test_classify_endpoint_rejects_bad_input():
    assert client.post("/api/classify", json={}).status_code == 400
    assert client.post("/api/classify", json={"pgn": "  "}).status_code == 400
    assert client.post("/api/classify", json={"pgn": "no games here"}).status_code == 400
    # One tiny game -> too few positions for a diagnosis
    tiny = '[White "A"]\n[Black "B"]\n\n1. e4 e5 2. Nf3 Nc6 1/2-1/2\n'
    assert client.post("/api/classify", json={"pgn": tiny}).status_code == 400


def test_classifier_page_serves():
    assert client.get("/classifier").status_code == 200


def test_heuristic_move_probs_is_distribution():
    board = chess.Board()
    for era in CFG_ERAS:
        probs = get_engine(era).move_probs(board)
        assert len(probs) == 20
        assert abs(sum(probs.values()) - 1.0) < 1e-9
        assert all(p > 0 for p in probs.values())


def test_eras_include_verdicts():
    eras = client.get("/api/eras").json()
    for era_id, era in eras.items():
        assert era.get("verdict"), f"{era_id} missing verdict copy"


LICHESS_GAME = """[Event "Rated blitz game"]
[Site "https://lichess.org/AbCd1234"]
[White "quorn_pieces"]
[Black "someone"]
[Date "2026.07.01"]
[Result "1-0"]

1. e4 e5 2. Nf3 d6 3. d4 Bg4 4. dxe5 Bxf3 5. Qxf3 dxe5 6. Bc4 Nf6 7. Qb3 Qe7
8. Nc3 c6 9. Bg5 b5 10. Nxb5 cxb5 11. Bxb5+ Nbd7 12. O-O-O Rd8 13. Rxd7 Rxd7
14. Rd1 Qe6 15. Bxd7+ Nxd7 16. Qb8+ Nxb8 17. Rd8# 1-0
"""


def test_game_url_propagates_to_characteristic_moves():
    games = classifier.parse_pgn_games(LICHESS_GAME)
    positions = classifier.sample_positions(games, "quorn_pieces")
    assert all(p["gameUrl"] == "https://lichess.org/AbCd1234" for p in positions)
    result = list(classifier.classify_stream(positions, CFG_ERAS, get_engine))[-1]
    for cm in result["characteristicMoves"].values():
        assert cm["gameUrl"] == "https://lichess.org/AbCd1234"
    # OTB-style Site headers (not URLs) must NOT produce links
    otb = classifier.parse_pgn_games(OPERA_GAME)
    assert all(p["gameUrl"] is None
               for p in classifier.sample_positions(otb, "Morphy, Paul"))
