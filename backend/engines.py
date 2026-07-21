"""Pluggable era engines.

- HeuristicEraEngine: placeholder with era-flavored move selection so the app
  is playable before any training. NOT the product — just scaffolding.
- Maia2Engine: integration point for fine-tuned Maia-2 checkpoints (Days 3-4).

Both expose: pick_move(board) -> chess.Move
"""
import math
import random

import chess

PIECE_VALUES = {
    chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3.2,
    chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0,
}
CENTER = {chess.D4, chess.E4, chess.D5, chess.E5}


class HeuristicEraEngine:
    def __init__(self, style: dict):
        self.t = style.get("temperature", 0.6)
        self.capture_bonus = style.get("capture_bonus", 0.3)
        self.check_bonus = style.get("check_bonus", 0.3)
        self.sac_tolerance = style.get("sacrifice_tolerance", 0.1)
        self.king_safety = style.get("king_safety_weight", 0.5)
        self.development = style.get("development_weight", 0.7)

    def score_move(self, board: chess.Board, move: chess.Move) -> float:
        score = 0.0
        piece = board.piece_at(move.from_square)

        # Material: value captured minus risk of losing the mover on arrival.
        if board.is_capture(move):
            victim = board.piece_at(move.to_square)
            victim_val = PIECE_VALUES.get(victim.piece_type, 1) if victim else 1  # en passant
            score += self.capture_bonus + 0.3 * victim_val
        board.push(move)
        try:
            if board.is_checkmate():
                return 100.0
            if board.is_check():
                score += self.check_bonus
            # Risk: did we leave the moved piece en prise?
            attackers = board.attackers(board.turn, move.to_square)
            defenders = board.attackers(not board.turn, move.to_square)
            if attackers and not defenders and piece:
                hang = PIECE_VALUES.get(piece.piece_type, 1)
                score -= hang * (1.0 - self.sac_tolerance)
        finally:
            board.pop()

        # Development: minors off the back rank in the opening.
        if board.fullmove_number <= 12 and piece:
            back = 0 if piece.color == chess.WHITE else 7
            if (piece.piece_type in (chess.KNIGHT, chess.BISHOP)
                    and chess.square_rank(move.from_square) == back):
                score += self.development * 0.5
            if move.to_square in CENTER:
                score += self.development * 0.3
        # King safety: reward castling, punish early king walks.
        if board.is_castling(move):
            score += self.king_safety * 1.2
        elif piece and piece.piece_type == chess.KING and board.fullmove_number <= 20:
            score -= self.king_safety * 0.8
        return score

    def pick_move(self, board: chess.Board) -> chess.Move:
        moves = list(board.legal_moves)
        scores = [self.score_move(board, m) for m in moves]
        # Softmax sampling with era temperature.
        mx = max(scores)
        weights = [math.exp((s - mx) / max(self.t, 0.05)) for s in scores]
        return random.choices(moves, weights=weights, k=1)[0]


class Maia2Engine:
    """Serve a fine-tuned Maia-2 era checkpoint (models/{era}.pt).

    Uses maia2.inference.inference_each, which handles black-to-move mirroring
    internally and returns a legal-move probability distribution. We temperature-
    sample from it (T<1 sharpens toward the era's most characteristic moves).
    NOMINAL_ELO must match scripts/prepare_training.py.
    """

    NOMINAL_ELO = 1900

    def __init__(self, checkpoint_path: str, temperature: float = 0.6,
                 opening_temperature: float = 1.0, opening_plies: int = 10):
        import torch
        from maia2 import model as maia2_model, inference

        self.temperature = temperature
        # Sample the model's true distribution in the opening: era character
        # lives in opening *diversity* (sharpening over-concentrates on 1.e4).
        self.opening_temperature = opening_temperature
        self.opening_plies = opening_plies
        self.net = maia2_model.from_pretrained(type="rapid", device="cpu")
        self.net.load_state_dict(torch.load(checkpoint_path, map_location="cpu"))
        self.net.eval()
        self._inference = inference
        self._prepared = inference.prepare()

    def pick_move(self, board: chess.Board) -> chess.Move:
        return self.pick_move_with_eval(board)[0]

    def pick_move_with_eval(self, board: chess.Board):
        """Returns (move, white_win_prob) — win prob from White's perspective."""
        move_probs, win_prob = self._inference.inference_each(
            self.net, self._prepared, board.fen(), self.NOMINAL_ELO, self.NOMINAL_ELO
        )
        t = self.opening_temperature if board.ply() < self.opening_plies else self.temperature
        moves, probs = zip(*move_probs.items())
        sharpened = [max(p, 1e-9) ** (1.0 / t) for p in probs]
        chosen = random.choices(moves, weights=sharpened, k=1)[0]
        return chess.Move.from_uci(chosen), win_prob
