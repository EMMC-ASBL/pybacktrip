""" Authors: Owain Beynon (UCL)
             Adham Hashibon (UCL) """

from typing import Union, Sequence
from tripper import Literal
from omikb.omikb import kb_toolbox
from typing import IO, TYPE_CHECKING
from typing import Literal as L
from typing import Union
import requests
from tripper import Literal

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import Generator

    from tripper.triplestore import Triple


class OmikbStrategy:
    __GRAPH = "graph://main"
    __CONTENT_TYPES = {"turtle": "text/turtle", "rdf": "application/rdf+xml"}
    __DEFAULT_NAMESPACES = {
        "owl": "http://www.w3.org/2002/07/owl#",
        "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
        "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
        "schema": "http://schema.org/",
    }

    def __init__(
        self, base_iri: str, triplestore_url: str, database: str, **kwargs
    ) -> None:
        """Initialise the OMIKB triplestore.

        Args:
            base_iri (str): Base IRI to initiate the triplestore from.
            triplestore_url (str): URL of the OMIKB service.
            database (str): Database of the OMIKB to be used.
            kwargs (object): Additional keyword arguments.
        """
        self.__namespaces = self.__DEFAULT_NAMESPACES.copy()
        self.__namespaces[""] = base_iri
        self.kb = kb_toolbox()  # Initialize your kb_toolbox here

    def triples(self, triple: "Triple") -> "Generator":
        """Retrieve triples matching a specific pattern."""
        # Implementation will depend on how kb_toolbox handles queries
        variables = [
            f"?{tripleName}"
            for tripleName, tripleValue in zip("spo", triple)
            if tripleValue is None
        ]
        if not variables:
            variables.append("*")
        whereSpec = " ".join(
            (
                f"?{tripleName}"
                if tripleValue is None
                else (
                    tripleValue
                    if tripleValue.startswith("<")
                    else (
                        "<{}{}>".format(self.__namespaces[""], tripleValue[1:])
                        if tripleValue.startswith(":")
                        else f"<{tripleValue}>"
                    )
                )
            )
            for tripleName, tripleValue in zip("spo", triple)
        )

        query = f"""
            SELECT {" ".join(variables)}
            FROM <{self.__GRAPH}>
            WHERE {{{whereSpec}}}
        """

        res = self.kb.query(self.format_query(query))

        for binding in res["results"]["bindings"]:
            yield tuple(
                (
                    self.__convert_json_entrydict(binding[name])
                    if name in binding
                    else value
                )
                for name, value in zip("spo", triple)
            )

    def add_triples(self, triples: Sequence["Triple"]) -> dict:
        """Add triples to the OMIKB."""
        # Construct the SPARQL update query for adding triples
        spec = " ".join(
            " ".join(
                (
                    value.n3()
                    if isinstance(value, Literal) and hasattr(value, "n3")
                    else (
                        value
                        if value.startswith("<") or value.startswith('"')
                        else (
                            "<{}{}>".format(self.__namespaces[""], value[1:])
                            if "" in self.__namespaces and value.startswith(":")
                            else str(value) if value.startswith(":") else f"<{value}>"
                        )
                    )
                )
                for value in triple
            )
            + " ."
            for triple in triples
        )

        cmd = f"INSERT DATA {{ GRAPH <{self.__GRAPH}> {{ {spec} }} }}"
        return self.kb.update(cmd)  # Assuming kb_toolbox has an update method

    def remove(self, triple: "Triple") -> object:
        """Remove triples from the OMIKB."""
        # Construct the SPARQL delete query
        spec = " ".join(
            (
                f"?{name}"
                if value is None
                else (
                    value.n3()
                    if isinstance(value, Literal)
                    else (
                        value
                        if value.startswith("<") or value.startswith('"')
                        else (
                            "<{}{}>".format(self.__namespaces[""], value[1:])
                            if value.startswith(":")
                            else f"<{value}>"
                        )
                    )
                )
            )
            for name, value in zip("spo", triple)
        )
        cmd = f"DELETE WHERE {{ GRAPH <{self.__GRAPH}> {{ { spec } }} }}"

        return self.kb.update(cmd)

    # def remove(self, subject: str, predicate: str, object: str) -> object:
    #     """Remove triples from the OMIKB."""
    #     cmd = f"DELETE WHERE {{ GRAPH <{self.__GRAPH}> {{ <{subject}> <{predicate}> <{object}> }} }}"
    #     return self.kb.update(cmd)

    # def query(self, query_object: str, **kwargs) -> list:
    #     """Execute a SPARQL query."""
    #     query = f"FROM <{self.__GRAPH}> {query_object}"
    #     return self.kb.query(query)

    def query(self, query_object: str, **kwargs):
        """Executes a SPARQL query against the OMIKB."""
        print(f"Executing SPARQL query: {query_object}")
        try:
            response = self.kb.query(self.format_query(query_object))
            if response.status_code == 400:
                print(f"Bad Request: {response.text}")  # Log the error response
                return None
            res = response.json()
        except Exception as e:
            print(f"Query execution failed: {e}")
            return None

        queryVars = res["head"]["vars"]
        queryBindings = res["results"]["bindings"]

        triplesRes = []
        for binding in queryBindings:
            currentTriple = ()
            for var in queryVars:
                currentTriple = currentTriple + (
                    self.__convert_json_entrydict(binding[var]),
                )
            triplesRes.append(currentTriple)
        
        print(f"Query result: {triplesRes}")

        return triplesRes

    def bind(self, prefix: str, namespace: str):
        """Bind a namespace."""
        if namespace:
            self.__namespaces[prefix] = namespace
        else:
            if prefix in self.__namespaces:
                del self.__namespaces[prefix]

    def namespaces(self) -> dict:
        """Get the SPARQL namespaces."""
        return self.__namespaces

    def parse(
        self,
        source: Union[str, IO] = "",
        location: str = "",
        data: str = "",
        format: str = "turtle",
        **kwargs,
    ):
        """
        Parse an ontology from a source and add the resulting triples to the triplestore.

        Args:
            source: File-like object or file name containing the ontology data.
            location: URL string pointing to the ontology source.
            data: String with ontology content directly.
            format: Format of the ontology (e.g., 'turtle', 'rdfxml', etc.).
            kwargs: Additional parameters to pass to the backend.

        Raises:
            ValueError: If none of 'source', 'location', or 'data' is provided.
        """

        # Ensure at least one input source is provided
        if not source and not location and not data:
            raise ValueError("One of 'source', 'location', or 'data' must be provided.")

        # Prioritize parsing from 'source', 'location', or 'data'
        if source:
            # If source is provided, handle file or file-like object
            self.kb.import_ontology(source, **kwargs)  # Remove format if not supported
        elif location:
            # If location (URL) is provided, fetch and parse the ontology from the URL
            self.kb.import_ontology(
                location, **kwargs
            )  # Remove format if not supported
        elif data:
            # If ontology data is provided as a string, parse it directly
            self.kb.import_ontology(
                data=data, **kwargs
            )  # Remove format if not supported

        print("Ontology parsing complete, triples added to the triplestore.")

    def serialize(
        self, destination: Union[str, IO] = "", format: str = "turtle", **kwargs
    ) -> str:
        """Serialise to destination.

        Arguments:
            destination: File name or object to write to. If not defined, the serialisation is returned.
            format: Format to serialise as. Supported formats, depends on the backend.
            kwargs: Additional backend-specific parameters controlling the serialisation.

        Returns:
            Serialised string if `destination` is not defined.
        """
        q = self.format_query(
            f"SELECT * WHERE {{ GRAPH <{self.__GRAPH}> {{ ?s ?p ?o }} }}"
        )
        print("QUERY: ", q)
        response = self.kb.query(q)
        
        if response.status_code == 400:
            print(f"Bad Request: {response.text}")  # Log the error response
            return None
        content = response.text

        if not destination:
            return content
        elif isinstance(destination, str):
            with open(destination, "w") as f:
                f.write(content)
        else:
            destination.write(content)

        return ""

    def format_query(self, query: str) -> str:
        """Format a SPARQL query with the namespaces."""
        for prefix, namespace in self.__namespaces.items():
            query = f"PREFIX {prefix}: <{namespace}> {query}"
        return query

    @classmethod
    def create_database(cls, database: str, **kwargs):
        """Create a new database in backend.

        Args:
            database (str): Name of the new database.
            kwargs: Keyword arguments passed to the backend create_database() method.
        """

        pass

    ## For OMIKB Backend this method could be dangerous

    @classmethod
    def remove_database(cls, triplestore_url: str, database: str, **kwargs):
        """Remove a database in backend.
    
        Args:
            triplestore_url (str): Endpoint of the triplestore.
            database (str): Name of the database to be removed.
            kwargs: Keyword arguments passed to the backend remove_database() method.
        """
    
        requests.delete(f"{triplestore_url}/{database}?graph={cls.__GRAPH}")

    @classmethod
    def list_databases(cls, **kwargs) -> str:
        """For backends that supports multiple databases, list of all
        databases.

        Args:
            kwargs: Keyword arguments passed to the backend list_database() method.
        """

        return cls.__GRAPH

    def __convert_json_entrydict(self, entrydict: dict) -> str:
        """Convert JSON entry dict in string format

        Args:
            entrydict (dict): Entry dict to be converted

        Raises:
            ValueError: Unexpected type in entrydict

        Returns:
            str: The entry dict correctly formatted as a string
        """

        if entrydict["type"] == "uri":
            if entrydict["value"].startswith(":"):
                return "<{}{}>".format(self.__namespaces[""], entrydict["value"][1:])
            else:
                return entrydict["value"]

        if entrydict["type"] == "literal":
            return Literal(
                entrydict["value"],
                lang=entrydict.get("xml:lang"),
                datatype=entrydict.get("datatype"),
            )

        if entrydict["type"] == "bnode":
            return (
                entrydict["value"]
                if entrydict["value"].startswith("_:")
                else f"_:{entrydict['value']}"
            )

        raise ValueError(f"Unexpected type in entrydict: {entrydict}")
