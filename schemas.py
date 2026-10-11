"""Schema Pydantic versionado para materiais educacionais: resumo, exercícios,
quiz, simulado (correção em lote), dicas e vídeos.

Lacuna conhecida e deliberada: diagramas SVG (presentes no material de
referência que originou este schema) não têm representação aqui. Modelar
geometria genérica (primitivas, rótulos, anotações) é um projeto à parte;
quando isso for necessário, a forma mais simples é um bloco que referencia
um arquivo estático (SVG/PNG) por caminho, não uma DSL de geometria.

Os modelos "públicos" (ExercicioPublico, QuestaoQuizPublica,
QuestaoSimuladoPublica) existem para que a API nunca devolva respostas
corretas antes de o aluno responder — ver routers/materiais.py. Eles são
construídos campo a campo (nunca via `model_dump(exclude=...)`), para que um
campo sensível novo, adicionado no futuro ao modelo completo, não vaze
silenciosamente por um `exclude` desatualizado. O Gabarito é a exceção
deliberada: lê o modelo completo e revela tudo, sob demanda (ver
material_para_gabarito), nunca a partir do payload da GET pública.
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
# Simulado — correção em lote (ver correcao.corrigir_simulado), não pergunta
# a pergunta como o quiz.
# --------------------------------------------------------------------------


class QuestaoSimulado(BaseModel):
    id: str
    pergunta: str
    opcoes: list[str]
    indice_correto: int
    # Opcional e aditivo: não aparece na correção em lote (que já é direta —
    # certo/errado + índice certo), mas alimenta o Gabarito.
    explicacao: str | None = None


class QuestaoSimuladoPublica(BaseModel):
    """Versão sem gabarito — nunca inclui indice_correto nem explicacao,
    igual a QuestaoQuizPublica."""

    id: str
    pergunta: str
    opcoes: list[str]


def simulado_para_publico(questao: QuestaoSimulado) -> QuestaoSimuladoPublica:
    return QuestaoSimuladoPublica(id=questao.id, pergunta=questao.pergunta, opcoes=questao.opcoes)


# --------------------------------------------------------------------------
# Dicas — sem gabarito, incluída na resposta pública tal como está.
# --------------------------------------------------------------------------


class Dica(BaseModel):
    id: str
    titulo: str
    texto: str | None = None
    itens: list[str] | None = None
    checklist: bool = False

    @model_validator(mode="after")
    def texto_itens_e_checklist_consistentes(self) -> "Dica":
        if self.checklist:
            if self.itens is None:
                raise ValueError("Dica com checklist=True precisa de 'itens'")
            if self.texto is not None:
                raise ValueError("Dica com checklist=True não deve ter 'texto'")
        elif (self.texto is None) == (self.itens is None):
            raise ValueError("Dica precisa de exatamente um entre 'texto' e 'itens'")
        return self


# --------------------------------------------------------------------------
# Vídeos — sem gabarito. O "link de sugestão" (URL completa + miniatura) é
# derivado do youtube_id inteiramente no frontend; não precisa de campo novo.
# --------------------------------------------------------------------------


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
    """O que GET /api/materiais/{id} devolve: capítulos/resumo e dicas/vídeos
    inalterados (não têm gabarito), exercícios/quiz/simulado nas versões
    públicas (sem resposta/indice_correto/explicacao)."""

    id: str
    metadados: Metadados
    capitulos: list[Capitulo]
    exercicios: list[ExercicioPublico]
    quiz: list[QuestaoQuizPublica]
    simulado: list[QuestaoSimuladoPublica]
    dicas: list[Dica]
    videos: list[Video]


def material_para_publico(material: MaterialEducacional) -> MaterialEducacionalPublico:
    return MaterialEducacionalPublico(
        id=material.id,
        metadados=material.metadados,
        capitulos=material.capitulos,
        exercicios=[exercicio_para_publico(e) for e in material.exercicios],
        quiz=[quiz_para_publico(q) for q in material.quiz],
        simulado=[simulado_para_publico(s) for s in material.simulado],
        dicas=material.dicas,
        videos=material.videos,
    )


# --------------------------------------------------------------------------
# Gabarito — view derivada do modelo COMPLETO (nunca do público). Não duplica
# dado nenhum no JSON de conteúdo; é só uma forma de leitura.
# --------------------------------------------------------------------------


class GabaritoItem(BaseModel):
    identificador: str  # numero do exercício (como string) ou id da questão
    enunciado: str
    resposta_formatada: str
    explicacao: str | None = None


class Gabarito(BaseModel):
    exercicios: list[GabaritoItem]
    quiz: list[GabaritoItem]
    simulado: list[GabaritoItem]


def _resposta_formatada(exercicio: Exercicio) -> str:
    r = exercicio.resposta
    if isinstance(r, RespostaNumerica) or isinstance(r, RespostaNumericaComId):
        return str(r.valor_esperado)
    if isinstance(r, RespostaCoordenadas):
        return "; ".join(f"{c.rotulo} {c.valor_esperado}" for c in r.campos)
    raise TypeError(f"tipo de resposta desconhecido: {type(r)!r}")


def material_para_gabarito(material: MaterialEducacional) -> Gabarito:
    return Gabarito(
        exercicios=[
            GabaritoItem(
                identificador=str(e.numero),
                enunciado=e.enunciado,
                resposta_formatada=_resposta_formatada(e),
                explicacao=e.explicacao,
            )
            for e in material.exercicios
        ],
        quiz=[
            GabaritoItem(
                identificador=q.id,
                enunciado=q.pergunta,
                resposta_formatada=q.opcoes[q.indice_correto],
                explicacao=q.explicacao,
            )
            for q in material.quiz
        ],
        simulado=[
            GabaritoItem(
                identificador=s.id,
                enunciado=s.pergunta,
                resposta_formatada=s.opcoes[s.indice_correto],
                explicacao=s.explicacao,
            )
            for s in material.simulado
        ],
    )
