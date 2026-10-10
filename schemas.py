"""Schema Pydantic versionado para materiais educacionais (resumo, exercícios,
quiz, e os modelos de simulado/dicas/vídeos — definidos para não quebrar o
schema depois, mas sem renderizador nesta etapa).

Lacuna conhecida e deliberada: diagramas SVG (presentes no material de
referência que originou este schema) não têm representação aqui. Modelar
geometria genérica (primitivas, rótulos, anotações) é um projeto à parte;
quando isso for necessário, a forma mais simples é um bloco que referencia
um arquivo estático (SVG/PNG) por caminho, não uma DSL de geometria.

Os modelos "públicos" (ExercicioPublico, QuestaoQuizPublica) existem para
que a API nunca devolva respostas corretas antes de o aluno responder — ver
routers/materiais.py. Eles são construídos campo a campo (nunca via
`model_dump(exclude=...)`), para que um campo sensível novo, adicionado no
futuro ao modelo completo, não vaze silenciosamente por um `exclude`
desatualizado.
"""

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, field_validator, model_validator

# --------------------------------------------------------------------------
# Metadados e raiz
# --------------------------------------------------------------------------


class Metadados(BaseModel):
    titulo: str
    disciplina: str
    ano_serie: str
    autor: str | None = None
    descricao: str | None = None


# --------------------------------------------------------------------------
# Resumo: Capítulo -> Seção -> blocos (união discriminada em "tipo")
# --------------------------------------------------------------------------

CorTom = Literal["azul", "verde-agua", "amarelo", "verde", "vermelho", "roxo"]


class BlocoParagrafo(BaseModel):
    tipo: Literal["paragrafo"]
    texto: str


class BlocoLista(BaseModel):
    tipo: Literal["lista"]
    itens: list[str]
    ordenada: bool = False


class BlocoDestaque(BaseModel):
    tipo: Literal["destaque"]
    tom: CorTom
    titulo: str
    texto: str | None = None
    itens: list[str] | None = None

    @model_validator(mode="after")
    def exatamente_texto_ou_itens(self) -> "BlocoDestaque":
        if (self.texto is None) == (self.itens is None):
            raise ValueError(
                "BlocoDestaque precisa de exatamente um entre 'texto' e 'itens'"
            )
        return self


class BlocoTabela(BaseModel):
    tipo: Literal["tabela"]
    titulo: str | None = None
    colunas: list[str]
    linhas: list[list[str]]

    @model_validator(mode="after")
    def linhas_batem_com_colunas(self) -> "BlocoTabela":
        n = len(self.colunas)
        for i, linha in enumerate(self.linhas):
            if len(linha) != n:
                raise ValueError(
                    f"linha {i} tem {len(linha)} valores, esperado {n} (nº de colunas)"
                )
        return self


class BlocoFormula(BaseModel):
    tipo: Literal["formula"]
    expressao: str
    legenda: str | None = None


BlocoResumo = Annotated[
    Union[BlocoParagrafo, BlocoLista, BlocoDestaque, BlocoTabela, BlocoFormula],
    Field(discriminator="tipo"),
]


class Secao(BaseModel):
    id: str
    titulo: str
    blocos: list[BlocoResumo] = []


class Capitulo(BaseModel):
    id: str
    titulo: str
    ordem: int
    secoes: list[Secao] = []


# --------------------------------------------------------------------------
# Exercícios: união discriminada em "tipo_resposta"
# --------------------------------------------------------------------------


class RespostaNumerica(BaseModel):
    tipo_resposta: Literal["num"]
    valor_esperado: float
    tolerancia: float = 0.0


class RespostaNumericaComId(BaseModel):
    tipo_resposta: Literal["numid"]
    campo_id: str
    valor_esperado: float
    tolerancia: float = 0.0


class CampoCoordenada(BaseModel):
    campo_id: str
    rotulo: str
    valor_esperado: float
    tolerancia: float = 0.0


class RespostaCoordenadas(BaseModel):
    tipo_resposta: Literal["coord"]
    campos: list[CampoCoordenada]


RespostaExercicio = Annotated[
    Union[RespostaNumerica, RespostaNumericaComId, RespostaCoordenadas],
    Field(discriminator="tipo_resposta"),
]


class Exercicio(BaseModel):
    id: str
    numero: int
    enunciado: str
    dica: str | None = None
    resposta: RespostaExercicio
    explicacao: str | None = None


class ExercicioPublico(BaseModel):
    """Versão sem gabarito de Exercicio — é isto, e só isto, que a rota
    GET /api/materiais/{id} devolve para exercícios."""

    id: str
    numero: int
    enunciado: str
    dica: str | None = None
    campos_entrada: list[dict[str, str]]  # [{"campo_id": ..., "rotulo": ...}, ...]


def _campos_entrada_de(resposta: RespostaExercicio) -> list[dict[str, str]]:
    if isinstance(resposta, RespostaNumerica):
        return [{"campo_id": "valor", "rotulo": ""}]
    if isinstance(resposta, RespostaNumericaComId):
        return [{"campo_id": resposta.campo_id, "rotulo": ""}]
    if isinstance(resposta, RespostaCoordenadas):
        return [{"campo_id": c.campo_id, "rotulo": c.rotulo} for c in resposta.campos]
    raise TypeError(f"tipo de resposta desconhecido: {type(resposta)!r}")


def exercicio_para_publico(exercicio: Exercicio) -> ExercicioPublico:
    return ExercicioPublico(
        id=exercicio.id,
        numero=exercicio.numero,
        enunciado=exercicio.enunciado,
        dica=exercicio.dica,
        campos_entrada=_campos_entrada_de(exercicio.resposta),
    )


# --------------------------------------------------------------------------
# Quiz
# --------------------------------------------------------------------------


class QuestaoQuiz(BaseModel):
    id: str
    categoria: str
    pergunta: str
    opcoes: list[str]
    indice_correto: int
    explicacao: str

    @field_validator("indice_correto")
    @classmethod
    def indice_dentro_do_range(cls, v: int, info) -> int:
        opcoes = info.data.get("opcoes")
        if opcoes is not None and not (0 <= v < len(opcoes)):
            raise ValueError(
                f"indice_correto={v} fora do range válido [0, {len(opcoes)})"
            )
        return v


class QuestaoQuizPublica(BaseModel):
    """Versão sem gabarito de QuestaoQuiz — o que GET /api/materiais/{id}
    devolve. Nunca inclui indice_correto nem explicacao."""

    id: str
    categoria: str
    pergunta: str
    opcoes: list[str]


def quiz_para_publico(questao: QuestaoQuiz) -> QuestaoQuizPublica:
    return QuestaoQuizPublica(
        id=questao.id,
        categoria=questao.categoria,
        pergunta=questao.pergunta,
        opcoes=questao.opcoes,
    )


# --------------------------------------------------------------------------
# Stubs — schema definido, sem renderizador nesta etapa
# --------------------------------------------------------------------------


class QuestaoSimulado(BaseModel):
    id: str
    pergunta: str
    opcoes: list[str]
    indice_correto: int


class Dica(BaseModel):
    id: str
    titulo: str
    texto: str | None = None
    itens: list[str] | None = None
    checklist: bool = False


class Video(BaseModel):
    id: str
    titulo: str
    descricao: str
    youtube_id: str


# --------------------------------------------------------------------------
# Raiz
# --------------------------------------------------------------------------


class MaterialEducacional(BaseModel):
    schema_version: Literal[1] = 1
    id: str
    metadados: Metadados
    capitulos: list[Capitulo] = []
    exercicios: list[Exercicio] = []
    quiz: list[QuestaoQuiz] = []
    simulado: list[QuestaoSimulado] = []
    dicas: list[Dica] = []
    videos: list[Video] = []


class MaterialEducacionalPublico(BaseModel):
    """O que GET /api/materiais/{id} devolve: capítulos/resumo inalterados
    (não têm gabarito), exercícios e quiz nas versões públicas (sem
    resposta/indice_correto/explicacao)."""

    id: str
    metadados: Metadados
    capitulos: list[Capitulo]
    exercicios: list[ExercicioPublico]
    quiz: list[QuestaoQuizPublica]


def material_para_publico(material: MaterialEducacional) -> MaterialEducacionalPublico:
    return MaterialEducacionalPublico(
        id=material.id,
        metadados=material.metadados,
        capitulos=material.capitulos,
        exercicios=[exercicio_para_publico(e) for e in material.exercicios],
        quiz=[quiz_para_publico(q) for q in material.quiz],
    )
