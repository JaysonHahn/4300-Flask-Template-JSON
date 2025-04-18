import os
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import nltk
from nltk.sentiment.vader import SentimentIntensityAnalyzer

nltk.download('vader_lexicon')

from data_loader import load_data, map_company_to_ticker
from preprocessing import weak_label
from models import create_classification_pipeline, create_ranking_pipeline
from analysis import SentimentAnalyzer

app = Flask(__name__)
CORS(app)

sid = SentimentIntensityAnalyzer()

df = load_data()
if "combined_text" not in df.columns:
    df["combined_text"] = df["title"] + " " + df["text"]

df["label"] = df["combined_text"].apply(weak_label)
df = df.dropna(subset=["label"])

clf_pipeline = create_classification_pipeline()
clf_pipeline.fit(df["combined_text"], df["label"])

rank_pipeline = create_ranking_pipeline()
rank_vectors = rank_pipeline.fit_transform(df["combined_text"])
df["rank_vector"] = list(rank_vectors)

sentiment_analyzer = SentimentAnalyzer(df, clf_pipeline, rank_pipeline)

@app.route("/")
def home():
    return render_template("base.html", title="Stock Sentiment, Search & Keyword Ranking App")

@app.route("/ask")
def ask():
    question = request.args.get("question", "").strip()
    if not question:
        return jsonify({"response": "No question provided"}), 400

    scores = sid.polarity_scores(question)
    compound = scores['compound']
    if compound >= 0.05:
        intent = "positive"
    elif compound <= -0.05:
        intent = "negative"
    else:
        intent = ""

    ticker = map_company_to_ticker(question)
    if not ticker:
        return jsonify({"response": "Company not recognized"}), 400

    sentiment_html = sentiment_analyzer.analyze_sentiment_for_ticker(ticker, intent=intent)
    return jsonify({"response": sentiment_html})

@app.route("/search")
def search():
    query = request.args.get("query", "").strip()
    if not query:
        return jsonify({"response": "No search query provided"}), 400
    results_html = sentiment_analyzer.search_documents(query, top_n=10)
    return jsonify({"results": results_html})

@app.route("/keywords")
def keywords():
    ticker = request.args.get("ticker", "").strip()
    if not ticker:
        return jsonify({"response": "No ticker provided"}), 400
    keywords_html = sentiment_analyzer.rank_keywords_for_ticker(ticker, top_n=10)
    return jsonify({"response": keywords_html})

@app.route("/rank")
def rank():
    ranking_html = sentiment_analyzer.rank_stocks()
    return jsonify({"response": ranking_html})

@app.route("/evaluate")
def evaluate():
    ticker = request.args.get("ticker", "").strip()
    if not ticker:
        return jsonify({"response": "No ticker provided"}), 400
    eval_html = sentiment_analyzer.train_and_evaluate_for_ticker(ticker)
    return jsonify({"response": eval_html})

@app.route("/vote", methods=["POST"])
def vote():
    data = request.get_json()
    post_id = data.get("post_id")
    vote_val = data.get("vote")  
    if not post_id or vote_val not in ["up", "down"]:
        return jsonify({"response": "Invalid vote data."}), 400

    from helpers.vote_helper import update_vote, get_vote_counts
    new_counts = update_vote(post_id, vote_val)
    return jsonify({"response": f"New vote counts - Upvotes: {new_counts[0]}, Downvotes: {new_counts[1]}."})

@app.route("/feedback", methods=["POST"])
def feedback():
    data = request.get_json()
    ticker = data.get("ticker", "").strip().upper()
    try:
        rating = float(data.get("rating", 3))  
    except ValueError:
        return jsonify({"response": "Invalid rating value."}), 400
    comments = data.get("comments", "").strip()
    if not ticker or not rating:
        return jsonify({"response": "Ticker or rating missing."}), 400

    from datetime import datetime
    feedback_row = {
        "ticker": ticker,
        "rating": rating,
        "comments": comments,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    import pandas as pd
    feedback_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "feedback.csv")
    if os.path.exists(feedback_file):
        existing_df = pd.read_csv(feedback_file)
        new_df = pd.concat([existing_df, pd.DataFrame([feedback_row])], ignore_index=True)
        new_df.to_csv(feedback_file, index=False)
    else:
        df_feedback = pd.DataFrame([feedback_row])
        df_feedback.to_csv(feedback_file, index=False)

    return jsonify({"response": f"Feedback saved for {ticker} with rating={rating}."})

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
