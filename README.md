# Elsevier Knowledge Platform Python SDK

A comprehensive Python SDK for programmatically accessing and integrating data from Elsevier’s premier knowledgebases, including **Resnet, Reaxys, Embase, Pharmapendium**, and more.

## Overview

This repository serves as a centralized hub for Elsevier data integration. It is designed to bridge various knowledgebases into a unified workflow, with a primary focus on the **ResnetAPI**, which provides programmatic access to the world’s largest molecular biology knowledge graph.

---

## The ResnetAPI

The **ResnetAPI** interfaces with the Pathway Studio relational database. It leverages the **Zeep** package for SOAP API communication and transforms relational data into high-performance graph representations using **NetworkX**.

### Core Components

* **Graph Object Query Language (GOQL):** All requests to the relational database are made via GOQL. You can build these queries using the `PathwayStudioGOQL.py` module or pass raw GOQL strings.
* **APISession Class:** This is the primary entry point for data retrieval. It handles iterative data fetching to ensure optimal network performance and stability for large datasets.
* **ResnetGraph Object:** Query results are loaded into an `APISession.Graph` object, which is a `ResnetGraph` class derived from `networkx.MultiDiGraph`.

### Customizing Data Retrieval

You can specify which entity and relation properties to load by modifying the session attributes:

* `APISession.relProps`: (Default: `['Name', 'RelationNumberOfReferences']`)
* `APISession.entProps`: (Default: `['Name']`)

Detailed documentation on property names and object types is available in the [Documentation folder](https://www.google.com/search?q=./ElsevierAPI/ResnetAPI/Documentation).

---

## Getting Started

### Prerequisites

To use these APIs, you must obtain credentials for the respective Elsevier services:

* **Pathway Studio (Resnet):** [Professional Services](https://www.elsevier.com/solutions/professional-services)
* **Reaxys:** [Contact Sales](https://www.elsevier.com/solutions/reaxys/contact-sales)
* **Embase & Pharmapendium:** Visit the [Elsevier Developer Portal](https://dev.elsevier.com). Swagger documentation is available [here](https://dev.elsevier.com/interactive.html).
* **Text-Mining API:** [Elsevier Text Mining Demo](https://demo.elseviertextmining.com)

### Configuration

1. Locate the `APIconfig.json` template in the `ElsevierAPI` folder.
2. Input your login credentials for each respective service.

### Installation

This SDK requires the following Python dependencies:

```bash
pip install zeep networkx requests pandas numpy rdflib xlsxwriter textblob scipy wheel openpyxl python-docx

```

---

## Integration Tools

* **Neo4j Export:** Use the `PSnx2Neo4j.py` module to import Resnet data retrieved via the API directly into a local Neo4j server instance for advanced graph visualization and querying.

