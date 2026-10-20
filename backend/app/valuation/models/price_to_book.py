"""Positive, economically meaningful common book equity × supported P/B."""

from app.valuation.validation import model, multiple, number, valued


@model
def calculate(inputs):
    shares = number(inputs, "shares", positive=True)
    book = number(inputs, "book_equity", positive=True)
    target = multiple(inputs, "target_pb")
    return valued(book / shares * target, {"book_value_per_share": book / shares,
                                           "target_pb": target, "book_basis": "supplied current common book equity"})
