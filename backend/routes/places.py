# backend/routes/places.py

import os
import httpx
from flask import Blueprint, request, jsonify, Response

places_bp = Blueprint("places", __name__)

GOOGLE_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY")


@places_bp.route("/api/places/nearby")
def nearby():
    lat     = request.args.get("lat")
    lng     = request.args.get("lng")
    radius  = request.args.get("radius", "5000")
    type_   = request.args.get("type", "hospital")
    keyword = request.args.get("keyword", "")

    url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
    params = {
        "location": f"{lat},{lng}",
        "radius":   radius,
        "type":     type_,
        "keyword":  keyword,
        "key":      GOOGLE_API_KEY,
    }
    resp = httpx.get(url, params=params)
    return jsonify(resp.json())


@places_bp.route("/api/places/geocode")
def geocode():
    lat = request.args.get("lat")
    lng = request.args.get("lng")

    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {"latlng": f"{lat},{lng}", "key": GOOGLE_API_KEY}
    resp = httpx.get(url, params=params)
    return jsonify(resp.json())


@places_bp.route("/api/places/photo")
def photo():
    """
    Proxies Google Places photo requests so the API key stays server-side.
    The frontend calls: /api/places/photo?ref=<photo_reference>
    """
    ref = request.args.get("ref")
    if not ref:
        return jsonify({"error": "ref is required"}), 400

    url = "https://maps.googleapis.com/maps/api/place/photo"
    params = {"maxwidth": "400", "photoreference": ref, "key": GOOGLE_API_KEY}

    # Google redirects to the actual image — follow the redirect
    resp = httpx.get(url, params=params, follow_redirects=True)
    return Response(
        resp.content,
        content_type=resp.headers.get("content-type", "image/jpeg"),
    )