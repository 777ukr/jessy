"""
Rating Controller for Jesse
Provides API endpoints for strategy rating with Ninja Score
"""

from typing import Optional
from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from jesse.services import auth as authenticator
from jesse.models.BacktestSession import get_backtest_sessions
from jesse.services.ninja_score import calculate_ninja_score, get_ninja_score_color

router = APIRouter(prefix="/rating", tags=["Rating"])


@router.post("/sessions")
def get_rated_sessions(
    request_json: dict = Body(default={}),
    authorization: Optional[str] = Header(None)
):
    """
    Get all backtest sessions with Ninja Score ratings
    
    Request body:
    {
        "limit": 100,
        "offset": 0,
        "status_filter": "finished",
        "min_ninja_score": null,
        "min_win_rate": null,
        "min_return": null,
        "min_profit_factor": null,
        "min_expectancy": null,
        "min_trades": null,
        "min_sharpe": null,
        "max_drawdown": null,
        "sort_by": "ninja_score",
        "sort_order": "desc"
    }
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()
    
    # Get filter parameters
    limit = request_json.get("limit", 100)
    offset = request_json.get("offset", 0)
    status_filter = request_json.get("status_filter", "finished")
    min_ninja_score = request_json.get("min_ninja_score")
    min_win_rate = request_json.get("min_win_rate")
    min_return = request_json.get("min_return")
    min_profit_factor = request_json.get("min_profit_factor")
    min_expectancy = request_json.get("min_expectancy")
    min_trades = request_json.get("min_trades")
    min_sharpe = request_json.get("min_sharpe")
    max_drawdown = request_json.get("max_drawdown")
    sort_by = request_json.get("sort_by", "ninja_score")
    sort_order = request_json.get("sort_order", "desc")
    
    # Get all finished sessions with optimized sorting
    try:
        sessions = get_backtest_sessions(
            limit=1000,  # Get more to filter
            offset=0,
            status_filter=status_filter,
            sort_by=sort_by if sort_by == 'ninja_score' else None,
            sort_order=sort_order
        )
    except Exception:
        # Fallback if sorting by ninja_score fails (field might not exist yet)
        sessions = get_backtest_sessions(
            limit=1000,
            offset=0,
            status_filter=status_filter
        )
    
    # Use cached Ninja Score or calculate if missing
    rated_sessions = []
    for session in sessions:
        if not session.metrics_json:
            continue
        
        try:
            metrics = session.metrics_json
            
            # Use cached ninja_score if available, otherwise calculate
            try:
                cached_score = session.ninja_score
                cached_category = session.ninja_category
            except (AttributeError, Exception):
                # Field might not exist yet
                cached_score = None
                cached_category = None
            
            if cached_score is not None and cached_category:
                ninja_data = {
                    'ninja_score': cached_score,
                    'category': cached_category,
                    'breakdown': {}  # Breakdown not cached, can be calculated if needed
                }
            else:
                # Calculate and cache for future use
                ninja_data = calculate_ninja_score(metrics)
                # Update session with calculated values (async, don't wait)
                try:
                    from jesse.models.BacktestSession import BacktestSession
                    BacktestSession.update(
                        ninja_score=ninja_data['ninja_score'],
                        ninja_category=ninja_data['category']
                    ).where(BacktestSession.id == session.id).execute()
                except Exception:
                    pass  # Don't fail if update fails
        except Exception:
            # Skip session if there's an error processing it
            continue
        
        # Extract strategy name from routes info (stored in state) or title
        strategy_name = session.title or "Unknown"
        
        # Try to get from state (routes info)
        if session.state:
            try:
                import json
                state = json.loads(session.state) if isinstance(session.state, str) else session.state
                if state and 'routes' in state and len(state['routes']) > 0:
                    # Get first route's strategy name
                    strategy_name = state['routes'][0].get('strategy', strategy_name)
            except Exception:
                pass
        
        # Fallback: use title if available
        if strategy_name == "Unknown" and session.title:
            strategy_name = session.title
        
        # Build session data with backtest report URL
        session_data = {
            "id": str(session.id),
            "strategy_name": strategy_name,
            "title": session.title or strategy_name,
            "description": session.description or "",
            "status": session.status,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
            "report_url": f"/#/backtest/{session.id}",
            "ninja_score": ninja_data["ninja_score"],
            "ninja_category": ninja_data["category"],
            "ninja_color": get_ninja_score_color(ninja_data["ninja_score"]),
            "metrics": {
                "total_trades": metrics.get("total_trades", 0),
                "win_rate": metrics.get("win_rate", 0.0),
                "total_net_profit": metrics.get("total_net_profit", 0.0),
                "total_net_profit_percentage": metrics.get("total_net_profit_percentage", 0.0),
                "max_drawdown_percentage": abs(metrics.get("max_drawdown_percentage", 0.0)),
                "sharpe_ratio": metrics.get("sharpe_ratio", 0.0),
                "sortino_ratio": metrics.get("sortino_ratio", 0.0),
                "calmar_ratio": metrics.get("calmar_ratio", 0.0),
                "expectancy": metrics.get("expectancy", 0.0),
                "profit_factor": metrics.get("profit_factor", 0.0),
                "cagr": metrics.get("cagr", 0.0),
                "starting_balance": metrics.get("starting_balance", 0.0),
                "finishing_balance": metrics.get("finishing_balance", 0.0),
            },
            "ninja_breakdown": ninja_data["breakdown"]
        }
        
        # Apply filters
        if min_ninja_score is not None and session_data["ninja_score"] < min_ninja_score:
            continue
        if min_win_rate is not None and session_data["metrics"]["win_rate"] < min_win_rate:
            continue
        if min_return is not None and session_data["metrics"]["total_net_profit_percentage"] < min_return:
            continue
        if min_profit_factor is not None and session_data["metrics"]["profit_factor"] < min_profit_factor:
            continue
        if min_expectancy is not None and session_data["metrics"]["expectancy"] < min_expectancy:
            continue
        if min_trades is not None and session_data["metrics"]["total_trades"] < min_trades:
            continue
        if min_sharpe is not None and session_data["metrics"]["sharpe_ratio"] < min_sharpe:
            continue
        if max_drawdown is not None and session_data["metrics"]["max_drawdown_percentage"] > max_drawdown:
            continue
        
        rated_sessions.append(session_data)
    
    # Sort sessions (use database sorting if possible for better performance)
    reverse = (sort_order == "desc")
    if sort_by == "ninja_score":
        # Already sorted by database query if using ninja_score index
        rated_sessions.sort(key=lambda x: x["ninja_score"], reverse=reverse)
    elif sort_by == "total_pnl":
        rated_sessions.sort(key=lambda x: x["metrics"]["total_net_profit"], reverse=reverse)
    elif sort_by == "return_pct":
        rated_sessions.sort(key=lambda x: x["metrics"]["total_net_profit_percentage"], reverse=reverse)
    elif sort_by == "win_rate":
        rated_sessions.sort(key=lambda x: x["metrics"]["win_rate"], reverse=reverse)
    elif sort_by == "sharpe":
        rated_sessions.sort(key=lambda x: x["metrics"]["sharpe_ratio"], reverse=reverse)
    elif sort_by == "profit_factor":
        rated_sessions.sort(key=lambda x: x["metrics"]["profit_factor"], reverse=reverse)
    elif sort_by == "expectancy":
        rated_sessions.sort(key=lambda x: x["metrics"]["expectancy"], reverse=reverse)
    elif sort_by == "trades":
        rated_sessions.sort(key=lambda x: x["metrics"]["total_trades"], reverse=reverse)
    
    # Apply pagination
    total_count = len(rated_sessions)
    paginated_sessions = rated_sessions[offset:offset + limit]
    
    # Calculate statistics
    if rated_sessions:
        avg_ninja_score = sum(s["ninja_score"] for s in rated_sessions) / len(rated_sessions)
        best_ninja_score = max(s["ninja_score"] for s in rated_sessions)
    else:
        avg_ninja_score = 0
        best_ninja_score = 0
    
    return JSONResponse({
        "sessions": paginated_sessions,
        "total_count": total_count,
        "filtered_count": len(rated_sessions),
        "statistics": {
            "total_strategies": total_count,
            "filtered_strategies": len(rated_sessions),
            "avg_ninja_score": round(avg_ninja_score, 2),
            "best_ninja_score": round(best_ninja_score, 2)
        }
    })


class UpdateSessionRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None

@router.put("/session/{session_id}")
def update_session_notes(session_id: str, request_json: UpdateSessionRequest, authorization: Optional[str] = Header(None)):
    """
    Update title and description for a backtest session
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()
    
    from jesse.models.BacktestSession import update_backtest_session_notes
    
    title = request_json.get('title', None)
    description = request_json.get('description', None)
    
    update_backtest_session_notes(session_id, title=title, description=description)
    
    return JSONResponse({'message': 'Session updated successfully'})


@router.get("/statistics")
def get_rating_statistics(authorization: Optional[str] = Header(None)):
    """
    Get overall rating statistics
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()
    
    try:
        sessions = get_backtest_sessions(limit=1000, status_filter="finished")
    except Exception:
        sessions = get_backtest_sessions(limit=1000, status_filter="finished")
    
    ninja_scores = []
    categories = {"Excellent": 0, "Good": 0, "Satisfactory": 0, "Poor": 0}
    
    for session in sessions:
        # Use cached ninja_score if available
        if session.ninja_score is not None:
            ninja_scores.append(session.ninja_score)
            if session.ninja_category:
                categories[session.ninja_category] = categories.get(session.ninja_category, 0) + 1
        elif session.metrics_json:
            # Calculate if not cached
            try:
                ninja_data = calculate_ninja_score(session.metrics_json)
                ninja_scores.append(ninja_data["ninja_score"])
                categories[ninja_data["category"]] += 1
            except Exception:
                continue
    
    return JSONResponse({
        "total_strategies": len(ninja_scores),
        "avg_ninja_score": round(sum(ninja_scores) / len(ninja_scores), 2) if ninja_scores else 0,
        "best_ninja_score": round(max(ninja_scores), 2) if ninja_scores else 0,
        "worst_ninja_score": round(min(ninja_scores), 2) if ninja_scores else 0,
        "categories": categories
    })

