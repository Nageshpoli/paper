from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from hashlib import sha256

import requests
from sqlalchemy.orm import Session

from app.db.models import UniverseConstituent, UniverseMember, UniverseSnapshot

NIFTY500_URL = "https://www.niftyindices.com/IndexConstituent/ind_nifty500list.csv"
NIFTY200_URL = "https://www.niftyindices.com/IndexConstituent/ind_nifty200list.csv"

INDUSTRY_TO_INDEX = {
    "bank": "NIFTY BANK", "banking": "NIFTY BANK", "banks": "NIFTY BANK",
    "information technology": "NIFTY IT", "software": "NIFTY IT", "it": "NIFTY IT",
    "automobile": "NIFTY AUTO", "automobiles": "NIFTY AUTO", "auto": "NIFTY AUTO",
    "pharmaceuticals": "NIFTY PHARMA", "pharma": "NIFTY PHARMA",
    "fmcg": "NIFTY FMCG", "consumer goods": "NIFTY FMCG",
    "metals": "NIFTY METAL", "metal": "NIFTY METAL",
    "realty": "NIFTY REALTY", "real estate": "NIFTY REALTY",
    "media": "NIFTY MEDIA", "energy": "NIFTY ENERGY",
    "financial services": "NIFTY FIN SERVICE",
}


class UniverseService:
    def refresh(self, db: Session, instruments: list[dict]) -> dict:
        return self._refresh(db, instruments, NIFTY500_URL, "NIFTY_500", 450)

    def refresh_nifty200(self, db: Session, instruments: list[dict]) -> dict:
        return self._refresh(db, instruments, NIFTY200_URL, "NIFTY_200", 180)

    def _refresh(self, db: Session, instruments: list[dict], source: str,
                 universe_name: str, minimum: int) -> dict:
        response = requests.get(source, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        rows = list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))))
        symbols = [r.get("Symbol", "").strip().upper() for r in rows]
        if len(symbols) < minimum or len(symbols) != len(set(symbols)) or "" in symbols:
            raise ValueError("Official constituent list failed count/uniqueness validation")
        by_symbol: dict[str, list[dict]] = {}
        for inst in instruments:
            if inst.get("instrument_type") == "EQ" and inst.get("segment") == "NSE":
                by_symbol.setdefault(inst["tradingsymbol"].upper(), []).append(inst)
        missing, ambiguous, mapped = [], [], []
        for row in rows:
            symbol = row["Symbol"].strip().upper()
            matches = by_symbol.get(symbol, [])
            if len(matches) != 1:
                (missing if not matches else ambiguous).append(symbol)
                continue
            industry = (row.get("Industry") or "").strip()
            mapped.append((symbol, int(matches[0]["instrument_token"]),
                           float(matches[0].get("tick_size") or 0.05),
                           industry or None,
                           INDUSTRY_TO_INDEX.get(industry.lower())))
        if len(mapped) < minimum:
            raise ValueError(f"{universe_name} mapping failed: {len(mapped)} mapped; "
                             f"missing={len(missing)} ambiguous={len(ambiguous)}")
        retrieved = datetime.now(timezone.utc).replace(tzinfo=None)
        version = sha256((universe_name + ":" + retrieved.date().isoformat() + ":"
                          + ",".join(sorted(symbols))).encode()).hexdigest()[:16]
        if not db.get(UniverseSnapshot, version):
            db.add(UniverseSnapshot(version=version, universe_name=universe_name,
                source=source, retrieved_at=retrieved, effective_date=retrieved.date().isoformat(),
                constituent_count=len(mapped)))
            db.flush()
            db.add_all([UniverseMember(version=version, universe_name=universe_name,
                symbol=s, instrument_token=t, tick_size=tick, sector=sector, sector_index=index)
                for s, t, tick, sector, index in mapped])
        if universe_name == "NIFTY_500":
            db.query(UniverseConstituent).delete()
            db.add_all([UniverseConstituent(symbol=s, instrument_token=t, tick_size=tick,
                sector=sector, sector_index=index, source=source, retrieved_at=retrieved,
                effective_date=retrieved.date().isoformat())
                for s, t, tick, sector, index in mapped])
        db.commit()
        return {"version": version, "count": len(mapped), "missing": missing, "ambiguous": ambiguous,
                "unmapped_sector": [s for s, _, _, _, idx in mapped if idx is None],
                "universe": universe_name, "retrieved_at": retrieved.isoformat()}
