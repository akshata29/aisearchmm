# Hybrid Search Setup Guide

This guide explains how to configure Azure AI Search for optimal hybrid search performance with RRF, semantic ranking, and scoring profiles when **not using the Knowledge Agent**.

## Quick Start

1. **Enable Hybrid Search** in the UI when Knowledge Agent is turned off
2. **Set Vector Weight** to balance text vs vector search (0.5 is a good start)
3. **Enable Semantic Ranker** (automatically enabled with hybrid search)
4. **Optionally enable Scoring Profile** for freshness/type boosts
5. **Test with Query Rewriting** for improved recall

## Overview

When not using the Knowledge Agent, this application implements advanced Azure AI Search features for optimal relevance:

1. **Hybrid Search**: Combines text search (BM25) and vector search with Reciprocal Rank Fusion (RRF)
2. **Semantic Ranking**: Applied after RRF to further improve relevance
3. **Scoring Profiles**: Applied after semantic ranking to boost based on freshness and document type
4. **Query Rewriting**: AI-powered generation of alternative query formulations

## Search Flow

```
User Query → [Query Rewriting] → Text Search + Vector Search → RRF → Semantic Ranker → Scoring Profile → Final Results
```

## Index Requirements

### Vector Field Configuration

Your index should include a vector field for embeddings:

```json
{
  "name": "content_vector",
  "type": "Collection(Edm.Single)",
  "dimensions": 1536,
  "searchable": true,
  "retrievable": false,
  "filterable": false,
  "facetable": false,
  "sortable": false,
  "vectorSearchProfile": "default-vector-profile"
}
```

### Semantic Configuration

Create a semantic configuration in your index:

```json
{
  "semantic": {
    "configurations": [
      {
        "name": "semantic-config",
        "prioritizedFields": {
          "titleField": {
            "fieldName": "document_title"
          },
          "prioritizedContentFields": [
            {
              "fieldName": "content_text"
            }
          ],
          "prioritizedKeywordsFields": [
            {
              "fieldName": "document_type"
            }
          ]
        },
        "rankingOrder": "boostedReRankerScore"
      }
    ]
  }
}
```

**Important**: The `"rankingOrder": "boostedReRankerScore"` setting ensures scoring profiles are applied AFTER semantic ranking (requires API version 2025-05-01-preview or newer).

### Scoring Profile Configuration

Create a scoring profile for freshness and document type boosts:

```json
{
  "scoringProfiles": [
    {
      "name": "freshness-scoring",
      "text": {
        "weights": {
          "content_text": 1.0,
          "document_title": 2.0
        }
      },
      "functions": [
        {
          "type": "freshness",
          "fieldName": "published_date",
          "boost": 2.0,
          "parameters": {
            "boostingDuration": "P365D"
          },
          "interpolation": "linear"
        },
        {
          "type": "tag",
          "fieldName": "document_type",
          "boost": 1.5,
          "parameters": {
            "tagsParameter": "docTypes"
          }
        }
      ],
      "functionAggregation": "sum"
    }
  ]
}
```

## Configuration Options

### Hybrid Search Settings

- **Use Hybrid Search**: Enables text + vector search with RRF
- **Vector Weight**: Controls balance between text (lower) and vector (higher) search
- **Max Text Recall Size**: Maximum text results for RRF (higher = better quality, slower)

### Vector Filter Options

- **Enable Vector Filters**: Useful for large datasets
- **Pre-filter**: Better recall, guarantees k results, slower
- **Post-filter**: Faster, may return fewer results

### Scoring Profile Settings

- **Use Scoring Profile**: Enables custom relevance boosting
- **Scoring Profile Name**: Must match a profile defined in your index

### Query Rewriting

- **Use Query Rewriting**: AI-powered query enhancement
- **Query Rewrite Count**: Number of alternative queries to generate (1-10)

## Performance Recommendations

### For Small Datasets (< 100K documents)
- Use pre-filtering for vector queries
- Enable query rewriting for better recall
- Use higher vector weights (0.7-0.8) if content is semantically rich

### For Medium Datasets (100K - 1M documents)
- Consider post-filtering for better performance
- Use balanced vector weights (0.4-0.6)
- Set max text recall size to 1500-2000

### For Large Datasets (> 1M documents)
- Use post-filtering for vector queries
- Lower vector weights (0.3-0.5) to favor text search precision
- Set max text recall size to 1000 or lower
- Consider using additional filters to reduce search scope

## API Version Requirements

- **Hybrid Search + RRF**: Available in all recent API versions
- **Semantic Ranking**: Requires Basic tier or higher
- **Query Rewriting**: Requires API version 2025-03-01-preview or newer
- **Scoring Profiles with Semantic**: Requires API version 2025-05-01-preview or newer

## Best Practices

1. **Always enable semantic ranking with hybrid search** for best results
2. **Use scoring profiles to maintain business rules** after semantic reranking
3. **Test different vector weights** with your specific data and queries
4. **Monitor performance** and adjust max text recall size accordingly
5. **Use query rewriting sparingly** - it adds latency but can improve recall

## Troubleshooting

### No Results Returned
- Check if vector field exists and is populated
- Verify semantic configuration name matches
- Ensure scoring profile name exists in index

### Poor Performance
- Reduce max text recall size
- Switch to post-filtering for vector queries
- Consider disabling query rewriting

### Unexpected Rankings
- Verify semantic configuration field mappings
- Check scoring profile function parameters
- Ensure `"rankingOrder": "boostedReRankerScore"` is set correctly
