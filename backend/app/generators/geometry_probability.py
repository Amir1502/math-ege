"""Authored, unreviewed course families for geometry and probability (slots 1–5).

Only integer/Fraction arithmetic defines mathematical values. Diagram coordinates
are presentation data. The central course builder owns materialising the bank.
"""

from copy import deepcopy
from fractions import Fraction
from math import comb
from typing import Any

from app.generators.base import Family, decimal_text, make_task
from app.schemas import ProfileSource

_TRIPLES = ((3, 4, 5), (5, 12, 13), (8, 15, 17), (7, 24, 25), (20, 21, 29))


def _seed(seed: int) -> None:
    if type(seed) is not int or not 0 <= seed <= 2**32 - 1:
        raise ValueError("Seed must be an unsigned 32-bit integer")


def _task(family_id: str, seed: int, profile: ProfileSource, **values: Any) -> dict:
    family = _BY_ID[family_id]
    return make_task(
        profile, family.slot, family.id, seed,
        title=family.title, skills=list(family.skill_ids), **values,
    )


def _triangle_exterior_angle(seed: int, profile: ProfileSource) -> dict:
    _seed(seed)
    alpha = 20 + seed % 50
    beta = 30 + (7 * seed + seed // 50) % 50
    exterior = alpha + beta
    return _task(
        "triangle-exterior-angle", seed, profile,
        statement=(
            f"В треугольнике ABC угол A равен {alpha}°, а внешний угол при вершине C, "
            f"смежный с внутренним углом C, равен {exterior}°. "
            "Найдите угол B. Ответ дайте в градусах."
        ),
        answer=beta,
        hints=[
            "Свяжите внешний угол с двумя внутренними углами, не смежными с ним.",
            "Внешний угол треугольника равен сумме углов A и B.",
            f"Из {exterior}° вычтите известный угол {alpha}°.",
        ],
        solution=[
            f"Внутренний угол C равен 180° − {exterior}° = {180 - exterior}°.",
            "Сумма внутренних углов треугольника равна 180°.",
            f"B = 180° − {alpha}° − {180 - exterior}° = {beta}°.",
            f"Проверка по теореме о внешнем угле: {alpha} + {beta} = {exterior}.",
        ],
    )


def _right_triangle_area(seed: int, profile: ProfileSource) -> dict:
    _seed(seed)
    scale = 1 + seed % 200
    x, y, z = _TRIPLES[(seed // 200) % len(_TRIPLES)]
    a, b, c = x * scale, y * scale, z * scale
    area = Fraction(a * b, 2)
    padding = scale * 2
    figure = {
        "description": "Треугольник ABC: угол A прямой, AB — данный катет, BC — гипотенуза.",
        "x_min": -padding, "x_max": a + padding,
        "y_min": -padding, "y_max": b + padding, "axes": False,
        "lines": [{"points": [
            {"x": 0, "y": 0}, {"x": a, "y": 0},
            {"x": 0, "y": b}, {"x": 0, "y": 0},
        ]}],
        "circles": [],
        "labels": [
            {"x": -scale, "y": -scale, "text": "A"},
            {"x": a + scale, "y": 0, "text": "B"},
            {"x": 0, "y": b + scale, "text": "C"},
        ],
    }
    return _task(
        "right-triangle-area", seed, profile,
        statement=(
            f"В прямоугольном треугольнике ABC угол A прямой, катет AB равен {a} см, "
            f"а гипотенуза BC равна {c} см. Найдите площадь треугольника в см²."
        ),
        answer=area, figure=figure,
        hints=[
            "Для площади нужны два перпендикулярных катета. Один пока неизвестен.",
            "По теореме Пифагора AC² = BC² − AB²; затем S = AB · AC / 2.",
            f"Вычислите AC² = {c * c} − {a * a} = {b * b} и извлеките корень.",
        ],
        solution=[
            f"AC² = {c}² − {a}² = {b * b}, поэтому AC = {b} см.",
            "Катеты перпендикулярны, поэтому один служит основанием, другой — высотой.",
            f"S = {a} · {b} / 2 = {decimal_text(area)} см².",
        ],
    )


def _trapezoid_area(seed: int, profile: ProfileSource) -> dict:
    _seed(seed)
    a = 4 + seed % 97
    b = a + 2 + 2 * ((seed // 97) % 29)
    height = 2 + (seed // 2813) % 47
    area = Fraction((a + b) * height, 2)
    return _task(
        "trapezoid-area", seed, profile,
        statement=(
            f"Основания трапеции равны {a} см и {b} см, а высота равна {height} см. "
            "Найдите площадь трапеции в см²."
        ),
        answer=area,
        hints=[
            "Площадь трапеции выражается через оба параллельных основания и высоту.",
            "S = (a + b)h / 2. Боковая сторона вместо высоты не подходит.",
            f"Полусумма оснований равна ({a} + {b}) / 2 = {(a + b) // 2} см.",
        ],
        solution=[
            f"Средняя линия трапеции равна ({a} + {b}) / 2 = {(a + b) // 2} см.",
            "Площадь равна произведению средней линии на высоту.",
            f"S = {(a + b) // 2} · {height} = {decimal_text(area)} см².",
        ],
        formula=r"S=\frac{a+b}{2}\,h",
    )


def _cyclic_quadrilateral_angle(seed: int, profile: ProfileSource) -> dict:
    _seed(seed)
    alpha = 40 + seed % 101
    answer = 180 - alpha
    return _task(
        "cyclic-quadrilateral-angle", seed, profile,
        statement=(
            "Выпуклый четырёхугольник ABCD вписан в окружность, вершины идут по "
            f"окружности в указанном порядке. Угол BAD равен {alpha}°. "
            "Найдите противоположный ему угол BCD. Ответ дайте в градусах."
        ),
        answer=answer,
        hints=[
            "Нужное свойство связано с тем, что все вершины лежат на одной окружности.",
            "Сумма противоположных углов вписанного четырёхугольника равна 180°.",
            f"Вычтите {alpha}° из 180°.",
        ],
        solution=[
            "Углы BAD и BCD опираются на две дуги BD, которые вместе дают окружность.",
            "Каждый вписанный угол равен половине соответствующей дуги; их сумма — 180°.",
            f"Угол BCD равен 180° − {alpha}° = {answer}°.",
        ],
    )


def _similar_triangles_area(seed: int, profile: ProfileSource) -> dict:
    _seed(seed)
    unit = 2 + seed % 17
    numerator = 2 + (seed // 17) % 3
    denominator = numerator + 1 + (seed // 51) % 3
    area_unit = 5 + seed % 15
    ab, ad = denominator * unit, numerator * unit
    full_area = denominator**2 * area_unit
    area = numerator**2 * area_unit
    ratio = Fraction(ad, ab)
    return _task(
        "similar-triangles-area", seed, profile,
        statement=(
            "В треугольнике ABC точка D лежит внутри стороны AB, точка E — внутри AC, "
            f"причём DE параллельна BC. Известно: AB = {ab} см, AD = {ad} см, "
            f"площадь ABC равна {full_area} см². Найдите площадь ADE в см²."
        ),
        answer=area,
        hints=[
            "Параллельность даёт равные углы, поэтому малый и большой треугольники подобны.",
            "Отношение площадей подобных треугольников равно квадрату отношения сторон.",
            f"Используйте S(ADE) = {full_area} · ({ad}/{ab})².",
        ],
        solution=[
            "Угол A общий, а углы ADE и ABC равны при параллельных DE и BC.",
            f"Треугольники подобны; отношение сторон малого к большому равно {ratio}.",
            f"S(ADE) = {full_area} · ({ad}/{ab})² = {area} см².",
            "Малый треугольник лежит внутри большого, поэтому его площадь меньше.",
        ],
        difficulty=2,
    )


def _intersecting_chords(seed: int, profile: ProfileSource) -> dict:
    _seed(seed)
    ce = 2 + (seed // 899) % 9
    ae = ce * (2 + seed % 31)
    eb = 3 + (seed // 31) % 29
    ed = ae * eb // ce
    return _task(
        "intersecting-chords", seed, profile,
        statement=(
            "Хорды AB и CD одной окружности пересекаются во внутренней точке E. "
            f"AE = {ae} см, EB = {eb} см, CE = {ce} см. Найдите ED в сантиметрах."
        ),
        answer=ed,
        hints=[
            "Используйте свойство отрезков двух пересекающихся хорд.",
            "Произведения отрезков одной хорды равны: AE · EB = CE · ED.",
            f"Неизвестный отрезок ED равен {ae} · {eb} / {ce}.",
        ],
        solution=[
            "Для пересекающихся внутри окружности хорд AE · EB = CE · ED.",
            f"ED = {ae} · {eb} / {ce} = {ed} см.",
            f"Проверка: оба произведения равны {ae * eb} см².",
        ],
        difficulty=2,
    )


def _displacement_length(seed: int, profile: ProfileSource) -> dict:
    _seed(seed)
    scale = 1 + seed % 100
    a, b, c = _TRIPLES[(seed // 100) % len(_TRIPLES)]
    sign = -1 if (seed // 500) % 2 else 1
    x = (seed // 1000) % 31 - 15
    y = (seed // 31000) % 31 - 15
    dx, dy = sign * a * scale, b * scale
    return _task(
        "displacement-length", seed, profile,
        statement=(
            f"В прямоугольной декартовой системе координат даны A({x}; {y}) и "
            f"B({x + dx}; {y + dy}). Найдите длину вектора AB в единицах длины."
        ),
        answer=c * scale,
        hints=[
            "Сначала найдите перемещения по двум координатным осям.",
            "AB = (x_B − x_A; y_B − y_A), а его длина — корень из суммы квадратов координат.",
            f"Координаты AB равны ({dx}; {dy}); вычислите √({dx * dx} + {dy * dy}).",
        ],
        solution=[
            f"Вычитаем начало из конца: AB = ({dx}; {dy}).",
            f"|AB|² = ({dx})² + ({dy})² = {(c * scale)**2}.",
            f"Длина неотрицательна: |AB| = {c * scale} единиц длины.",
        ],
        formula=r"|\overrightarrow{AB}|=\sqrt{(x_B-x_A)^2+(y_B-y_A)^2}",
    )


def _vector_sum_length(seed: int, profile: ProfileSource) -> dict:
    _seed(seed)
    ax = seed % 17 - 8
    ay = (seed // 17) % 19 - 9
    scale = 1 + seed % 23
    bx, by = 3 * scale - ax, 4 * scale - ay
    return _task(
        "vector-sum-length", seed, profile,
        statement=(
            f"Даны векторы a = ({ax}; {ay}) и b = ({bx}; {by}) в прямоугольной "
            "декартовой системе координат. Найдите длину вектора a + b."
        ),
        answer=5 * scale,
        hints=[
            "Складывать нужно соответствующие координаты, а не длины векторов.",
            "a + b = (a_x + b_x; a_y + b_y); затем примените формулу длины.",
            f"Сумма векторов имеет координаты ({3 * scale}; {4 * scale}).",
        ],
        solution=[
            f"a + b = ({ax} + ({bx}); {ay} + ({by})) = ({3 * scale}; {4 * scale}).",
            f"|a + b| = √({(3 * scale)**2} + {(4 * scale)**2}) = {5 * scale}.",
            "Сложение модулей дало бы длину ломаной, а не искомого перемещения.",
        ],
        formula=r"|a+b|=\sqrt{(a_x+b_x)^2+(a_y+b_y)^2}",
    )


def _vector_scaled_difference(seed: int, profile: ProfileSource) -> dict:
    _seed(seed)
    ax, ay = 2 + seed % 37, (seed // 37) % 41 - 20
    bx, by = (seed // 1517) % 29 - 14, 1 + seed % 19
    factor = 2 + (seed // 43993) % 7
    answer = ay - factor * by
    return _task(
        "vector-scaled-difference", seed, profile,
        statement=(
            f"Даны векторы a = ({ax}; {ay}), b = ({bx}; {by}) и число k = {factor}. "
            "Найдите вторую координату вектора a − kb."
        ),
        answer=answer,
        hints=[
            "Сначала умножьте вектор b на число, затем выполните вычитание.",
            "Каждая координата b умножается на k; вторая координата разности равна a_y − kb_y.",
            f"Подставьте вторые координаты: {ay} − {factor} · {by}.",
        ],
        solution=[
            f"kb = ({factor * bx}; {factor * by}).",
            f"a − kb = ({ax - factor * bx}; {answer}).",
            f"Требуется только вторая координата: {answer}.",
        ],
        formula=r"(a-kb)_y=a_y-kb_y",
    )


def _vector_dot_product(seed: int, profile: ProfileSource) -> dict:
    _seed(seed)
    ax, ay = seed % 101 - 50, (seed // 101) % 97 - 48
    bx, by = 2 + (seed // 9797) % 31, 1 + (seed // 303707) % 29
    answer = ax * bx + ay * by
    return _task(
        "vector-dot-product", seed, profile,
        statement=(
            f"В прямоугольной декартовой системе координат даны векторы a = ({ax}; {ay}) "
            f"и b = ({bx}; {by}). Найдите их скалярное произведение."
        ),
        answer=answer,
        hints=[
            "Скалярное произведение — число, а не пара координат.",
            "Умножьте первые координаты, умножьте вторые и сложите результаты.",
            f"Вычислите ({ax}) · ({bx}) + ({ay}) · ({by}).",
        ],
        solution=[
            "В прямоугольном ортонормированном базисе a · b = a_xb_x + a_yb_y.",
            f"Произведения координат: {ax * bx} и {ay * by}.",
            f"Их сумма равна {answer}. Скалярное произведение может быть отрицательным.",
        ],
        formula=r"a\cdot b=a_xb_x+a_yb_y",
    )


def _vector_angle(seed: int, profile: ProfileSource) -> dict:
    _seed(seed)
    ax, ay = 1 + seed % 31, 2 + (seed // 31) % 29
    scale = 1 + (seed // 155) % 5
    index = seed % 5
    rotations = ((ax, ay), (ax - ay, ax + ay), (-ay, ax), (-ax - ay, ax - ay), (-ax, -ay))
    bx, by = (coordinate * scale for coordinate in rotations[index])
    angle = (0, 45, 90, 135, 180)[index]
    cosine = ("1", "√2/2", "0", "−√2/2", "−1")[index]
    dot = ax * bx + ay * by
    return _task(
        "vector-angle", seed, profile,
        statement=(
            f"Даны ненулевые векторы a = ({ax}; {ay}) и b = ({bx}; {by}) "
            "в прямоугольной декартовой системе координат. "
            "Найдите угол между ними в градусах, от нуля до развёрнутого угла включительно."
        ),
        answer=angle,
        hints=[
            "Выразите косинус угла через скалярное произведение и длины.",
            "cos φ = (a · b) / (|a||b|); обе длины положительны.",
            f"a · b = {dot}, |a|² = {ax * ax + ay * ay}, |b|² = {bx * bx + by * by}.",
        ],
        solution=[
            f"a · b = {dot}; квадраты длин равны {ax * ax + ay * ay} и {bx * bx + by * by}.",
            f"Подставив их в формулу косинуса и сократив точные корни, получаем cos φ = {cosine}.",
            f"На промежутке от 0° до 180° этому косинусу соответствует угол {angle}°.",
        ],
        formula=r"\cos\varphi=\frac{a\cdot b}{|a|\,|b|}",
        difficulty=2,
    )


def _right_prism_volume(seed: int, profile: ProfileSource) -> dict:
    _seed(seed)
    a, b = 2 + seed % 89, 3 + (seed // 89) % 83
    height = 1 + (seed // 7387) % 79
    area = Fraction(a * b, 2)
    volume = area * height
    return _task(
        "right-prism-volume", seed, profile,
        statement=(
            "Основание прямой призмы — прямоугольный треугольник с катетами "
            f"{a} см и {b} см. Высота призмы равна {height} см. "
            "Найдите объём призмы в см³."
        ),
        answer=volume,
        hints=[
            "Объём призмы равен площади её основания, умноженной на высоту призмы.",
            "Площадь прямоугольного треугольника равна половине произведения катетов.",
            f"Вычислите V = ({a} · {b} / 2) · {height}.",
        ],
        solution=[
            f"S основания = {a} · {b} / 2 = {decimal_text(area)} см².",
            f"V = S основания · h = {decimal_text(area)} · {height} = {decimal_text(volume)} см³.",
            "Высота призмы — расстояние между плоскостями оснований.",
        ],
        formula=r"V=S_{\text{осн}}h=\frac{ab}{2}h",
    )


def _rectangular_box_surface(seed: int, profile: ProfileSource) -> dict:
    _seed(seed)
    a, b, c = 1 + seed % 79, 2 + (seed // 79) % 73, 3 + (seed // 5767) % 67
    answer = 2 * (a * b + a * c + b * c)
    return _task(
        "rectangular-box-surface", seed, profile,
        statement=(
            f"Три измерения прямоугольного параллелепипеда равны {a} см, {b} см и {c} см. "
            "Найдите площадь его полной поверхности в см², включая все грани."
        ),
        answer=answer,
        hints=[
            "У прямоугольного параллелепипеда три пары равных противоположных граней.",
            "Полная поверхность S = 2(ab + ac + bc).",
            f"Площади трёх разных граней равны {a * b}, {a * c} и {b * c} см².",
        ],
        solution=[
            f"Две грани имеют площадь {a * b} см² каждая, ещё две — {a * c} см².",
            f"Последняя пара имеет площадь {b * c} см² каждой грани.",
            f"S = 2 · ({a * b} + {a * c} + {b * c}) = {answer} см².",
        ],
        formula=r"S_{\text{полн}}=2(ab+ac+bc)",
    )


def _square_pyramid_volume(seed: int, profile: ProfileSource) -> dict:
    _seed(seed)
    side, height = 2 + seed % 31, 3 * (1 + (seed // 31) % 19)
    volume = Fraction(side**2 * height, 3)
    return _task(
        "square-pyramid-volume", seed, profile,
        statement=(
            f"Основание пирамиды — квадрат со стороной {side} см. Перпендикуляр "
            f"из вершины к плоскости основания имеет длину {height} см. "
            "Найдите объём пирамиды в см³."
        ),
        answer=volume,
        hints=[
            "Данный перпендикуляр — высота пирамиды, а не боковое ребро.",
            "Объём пирамиды равен одной трети произведения площади основания на высоту.",
            f"Площадь квадрата равна {side**2} см²; умножьте её на {height} и разделите на три.",
        ],
        solution=[
            f"S основания = {side}² = {side**2} см².",
            f"V = {side**2} · {height} / 3 = {decimal_text(volume)} см³.",
            "Положение основания высоты внутри или вне квадрата не меняет формулу объёма.",
        ],
        formula=r"V=\frac13 S_{\text{осн}}h",
    )


def _cylinder_volume_coefficient(seed: int, profile: ProfileSource) -> dict:
    _seed(seed)
    radius, height = 1 + seed % 37, 2 + (seed // 37) % 29
    coefficient = radius**2 * height
    return _task(
        "cylinder-volume-coefficient", seed, profile,
        statement=(
            f"Радиус основания прямого кругового цилиндра равен {radius} см, "
            f"его высота равна {height} см. Объём цилиндра записан как V = kπ см³. "
            "Найдите число k."
        ),
        answer=coefficient,
        hints=[
            "Объём цилиндра равен площади круга основания, умноженной на высоту.",
            "V = πr²h. В ответе просят только коэффициент при π, то есть r²h.",
            f"Вычислите {radius}² · {height}; приближённое значение π не нужно.",
        ],
        solution=[
            f"Площадь основания равна {radius**2}π см².",
            f"V = {radius**2}π · {height} = {coefficient}π см³.",
            f"Следовательно, k = {coefficient}. Ответ — коэффициент, а не приближение объёма.",
        ],
        formula=r"V=\pi r^2h,\qquad k=r^2h",
    )


def _cone_surface_coefficient(seed: int, profile: ProfileSource) -> dict:
    _seed(seed)
    scale = 1 + seed % 59
    radius, height, slant = 3 * scale, 4 * scale, 5 * scale
    coefficient = radius * (radius + slant)
    return _task(
        "cone-surface-coefficient", seed, profile,
        statement=(
            f"У прямого кругового конуса радиус основания равен {radius} см, "
            f"высота равна {height} см. Площадь полной поверхности, включая основание, "
            "записана как S = kπ см². Найдите число k."
        ),
        answer=coefficient,
        hints=[
            "В формуле боковой поверхности нужна образующая, которую можно найти по высоте и "
            "радиусу.",
            "l² = r² + h²; полная поверхность S = πrl + πr².",
            f"Образующая равна √({radius**2} + {height**2}) = {slant} см. Найдите r(l + r).",
        ],
        solution=[
            f"В осевом сечении l = √({radius}² + {height}²) = {slant} см.",
            f"Боковая поверхность равна {radius * slant}π см², основание — {radius**2}π см².",
            f"Итого S = {coefficient}π см²; искомый коэффициент k = {coefficient}.",
        ],
        formula=r"l=\sqrt{r^2+h^2},\qquad S_{\text{полн}}=\pi r(l+r)",
        difficulty=2,
    )


def _sphere_volume_coefficient(seed: int, profile: ProfileSource) -> dict:
    _seed(seed)
    radius = 3 * (1 + seed % 71)
    coefficient = Fraction(4 * radius**3, 3)
    return _task(
        "sphere-volume-coefficient", seed, profile,
        statement=(
            f"Радиус шара равен {radius} см. Его объём записан как V = kπ см³. "
            "Найдите число k."
        ),
        answer=coefficient,
        hints=[
            "Нужен объём шара, а не площадь его сферической поверхности.",
            "V = 4πr³ / 3, поэтому k = 4r³ / 3.",
            f"Возведите {radius} в куб, умножьте на четыре и разделите на три.",
        ],
        solution=[
            f"Радиус в кубе: {radius}³ = {radius**3} см³.",
            f"V = 4 · {radius**3} · π / 3 = {decimal_text(coefficient)}π см³.",
            f"Коэффициент k равен {decimal_text(coefficient)}; число π не округляем.",
        ],
        formula=r"V=\frac43\pi r^3",
    )


def _solid_similarity_volume(seed: int, profile: ProfileSource) -> dict:
    _seed(seed)
    small = 2 + seed % 17
    large = small + 1 + (seed // 17) % 7
    unit = 2 + (seed // 119) % 13
    small_volume, large_volume = small**3 * unit, large**3 * unit
    return _task(
        "solid-similarity-volume", seed, profile,
        statement=(
            "Две прямые призмы подобны. Соответствующие рёбра меньшей и большей призм "
            f"равны {small} см и {large} см. Объём меньшей призмы равен {small_volume} см³. "
            "Найдите объём большей призмы в см³."
        ),
        answer=large_volume,
        hints=[
            "При подобии изменяются все три линейных измерения, а не только одно ребро.",
            "Объёмы подобных тел относятся как кубы соответствующих длин.",
            f"Умножьте {small_volume} на ({large}/{small})³.",
        ],
        solution=[
            f"Коэффициент подобия от меньшей призмы к большей равен {large}/{small}.",
            "Площадь основания увеличивается в квадрат этого коэффициента, высота — в сам "
            "коэффициент.",
            f"V большей = {small_volume} · ({large}/{small})³ = {large_volume} см³.",
        ],
        formula=r"\frac{V_{\text{б}}}{V_{\text{м}}}=\left(\frac{a_{\text{б}}}{a_{\text{м}}}\right)^3",
        difficulty=2,
    )


def _urn_favorable_count(seed: int, profile: ProfileSource) -> dict:
    _seed(seed)
    total = (20, 25, 40, 50, 100)[(seed // 19) % 5]
    red = 1 + seed % (total - 1)
    blue = total - red
    probability = Fraction(red, total)
    return _task(
        "urn-favorable-count", seed, profile,
        statement=(
            "В непрозрачном мешке одинаковые на ощупь шары: "
            f"красных — {red}, синих — {blue}. "
            "Каждый шар имеет одинаковую вероятность быть вынутым. "
            "Наугад вынимают один шар. Найдите вероятность того, что он красный."
        ),
        answer=probability,
        hints=[
            "Равновозможные исходы — отдельные шары, а не два названия цветов.",
            "Разделите число красных шаров на общее число шаров.",
            f"Всего {red} + {blue} = {total} шаров; благоприятных исходов — {red}.",
        ],
        solution=[
            f"Общее число равновозможных исходов равно {total}.",
            f"Благоприятных исходов: {red}. В каждом из них выбран красный шар.",
            f"P = {red}/{total} = {decimal_text(probability)}.",
        ],
        formula=r"P(A)=\frac{m}{n}",
    )


def _integer_event_boundaries(seed: int, profile: ProfileSource) -> dict:
    _seed(seed)
    total = (50, 100, 200, 400, 1000)[(seed // 47) % 5]
    lower = 1 + seed % (total // 2)
    upper = total // 2 + 1 + (seed // (total // 2)) % (total - total // 2)
    count = upper - lower
    probability = Fraction(count, total)
    return _task(
        "integer-event-boundaries", seed, profile,
        statement=(
            f"Карточки пронумерованы от 1 до {total} включительно. Наугад выбирают одну, "
            "причём все карточки равновероятны. Найдите вероятность того, что её номер "
            f"больше {lower}, но не превосходит {upper}."
        ),
        answer=probability,
        hints=[
            "Переведите два словесных ограничения в неравенства и проверьте обе границы.",
            "Нижняя граница не включается, верхняя включается: lower < X ≤ upper.",
            f"Подходят целые числа от {lower + 1} до {upper}; их {upper} − {lower}.",
        ],
        solution=[
            f"Событие задаётся неравенствами {lower} < X ≤ {upper}.",
            f"Число подходящих карточек: {upper} − ({lower} + 1) + 1 = {count}.",
            f"P = {count}/{total} = {decimal_text(probability)}.",
        ],
        formula=r"P(l<X\le u)=\frac{u-l}{N}\quad (l,u\in\mathbb Z)",
    )


def _complement_quality(seed: int, profile: ProfileSource) -> dict:
    _seed(seed)
    defective = Fraction(1 + seed % 999, 1000)
    good = 1 - defective
    return _task(
        "complement-quality", seed, profile,
        statement=(
            "Изделие бывает либо годным, либо бракованным; третьего исхода нет. "
            f"Вероятность того, что случайно выбранное изделие бракованное, равна "
            f"{decimal_text(defective)}. Найдите вероятность выбрать годное изделие."
        ),
        answer=good,
        hints=[
            "Годность и брак здесь являются противоположными событиями.",
            "Вероятности противоположных событий в сумме равны единице.",
            f"Вычислите 1 − {decimal_text(defective)}.",
        ],
        solution=[
            "Из условия следует, что годные и бракованные изделия исчерпывают все исходы.",
            f"P(годное) = 1 − P(брак) = 1 − {decimal_text(defective)}.",
            f"Искомая вероятность равна {decimal_text(good)}.",
        ],
        formula=r"P(\overline A)=1-P(A)",
    )


def _coin_pattern_enumeration(seed: int, profile: ProfileSource) -> dict:
    _seed(seed)
    tosses = 3 + seed % 4
    heads = 1 + (seed // 4) % tosses
    favorable = comb(tosses, heads)
    probability = Fraction(favorable, 2**tosses)
    toss_word = "раза" if tosses in (3, 4) else "раз"
    head_word = "раза" if heads in (2, 3, 4) else "раз"
    return _task(
        "coin-pattern-enumeration", seed, profile,
        statement=(
            f"Симметричную монету независимо подбрасывают {tosses} {toss_word}. "
            f"Найдите вероятность того, что орёл выпадет ровно {heads} {head_word}."
        ),
        answer=probability,
        hints=[
            "Элементарный исход — вся упорядоченная последовательность орлов и решек.",
            f"Всего 2^{tosses} равновозможных последовательностей; отберите нужное число орлов.",
            f"Выпишите все варианты и оставьте те, где число орлов равно {heads}.",
        ],
        solution=[
            f"Общее число последовательностей: {2**tosses}. "
            f"На каждом из {tosses} мест два варианта.",
            f"Число орлов должно равняться {heads}; подходящих последовательностей {favorable}.",
            f"P = {favorable}/{2**tosses} = {decimal_text(probability)}.",
            "Другие количества орлов не включаются: в условии сказано «ровно».",
        ],
        formula=r"P(A)=\frac{\text{число подходящих последовательностей}}{2^n}",
    )


def _spinner_sector(seed: int, profile: ProfileSource) -> dict:
    _seed(seed)
    angle = 9 * (1 + seed % 39)
    probability = Fraction(angle, 360)
    return _task(
        "spinner-sector", seed, profile,
        statement=(
            "Стрелка кругового указателя после вращения останавливается с равномерным "
            f"распределением направления. Красный сектор имеет центральный угол {angle}°. "
            "Остальная часть круга синяя. Вероятность остановки точно на границе равна нулю. "
            "Найдите вероятность остановки в красном секторе."
        ),
        answer=probability,
        hints=[
            "При равномерном направлении вероятность пропорциональна величине угла сектора.",
            "Полный оборот составляет 360°, поэтому P = α / 360°.",
            f"Разделите угол {angle}° на 360° и сократите дробь.",
        ],
        solution=[
            "Равным угловым промежуткам соответствуют одинаковые вероятности.",
            f"Красный сектор занимает {angle}/360 полного оборота.",
            f"P = {angle}/360 = {decimal_text(probability)}; граничные лучи вероятность не меняют.",
        ],
        formula=r"P=\frac{\alpha}{360^\circ}",
    )


def _independent_at_least_one(seed: int, profile: ProfileSource) -> dict:
    _seed(seed)
    first = Fraction(5 + seed % 91, 100)
    second = Fraction(10 + (seed // 91) % 81, 100)
    neither = (1 - first) * (1 - second)
    probability = 1 - neither
    return _task(
        "independent-at-least-one", seed, profile,
        statement=(
            "Два датчика обнаруживают сигнал независимо друг от друга. Вероятность "
            f"обнаружения первым датчиком равна {decimal_text(first)}, вторым — "
            f"{decimal_text(second)}. Найдите вероятность, что сигнал обнаружит хотя бы один "
            "датчик."
        ),
        answer=probability,
        hints=[
            "Событию «хотя бы один» противоположно событие «ни один».",
            "Независимость позволяет умножить вероятности двух необнаружений.",
            f"Вычислите 1 − (1 − {decimal_text(first)}) · (1 − {decimal_text(second)}).",
        ],
        solution=[
            f"Вероятности необнаружения равны {decimal_text(1 - first)} и "
            f"{decimal_text(1 - second)}.",
            f"По независимости P(ни один) = {decimal_text(neither)}.",
            f"P(хотя бы один) = 1 − {decimal_text(neither)} = {decimal_text(probability)}.",
        ],
        formula=r"P(A\cup B)=1-(1-P(A))(1-P(B))",
        difficulty=2,
    )


def _conditional_without_replacement(seed: int, profile: ProfileSource) -> dict:
    _seed(seed)
    total = (21, 26, 41, 51, 81, 101)[(seed // 19) % 6]
    red = 2 + seed % (total - 2)
    probability = Fraction(red - 1, total - 1)
    return _task(
        "conditional-without-replacement", seed, profile,
        statement=(
            f"В коробке одинаковые на ощупь шары; всего их {total}, "
            f"из них красных — {red}, остальные синие. "
            "Шары по одному выбирают равновероятно без возвращения. Известно, что первый "
            "вынутый шар красный. Найдите условную вероятность того, что второй шар тоже красный."
        ),
        answer=probability,
        hints=[
            "Условие о первом шаре уже известно: пересчитайте состав оставшейся коробки.",
            "После красного шара осталось на один шар меньше всего и на один красный меньше.",
            f"Второй выбор происходит среди {total - 1} шаров, из них красных {red - 1}.",
        ],
        solution=[
            f"Красных шаров осталось {red - 1}; общее число оставшихся шаров — {total - 1}.",
            f"P(второй красный | первый красный) = {red - 1}/{total - 1} = "
            f"{decimal_text(probability)}.",
            "Умножать на вероятность первого красного не нужно: спрашивается условная вероятность.",
        ],
        formula=r"P(R_2\mid R_1)=\frac{r-1}{N-1}",
        difficulty=2,
    )


def _overlapping_event_union(seed: int, profile: ProfileSource) -> dict:
    _seed(seed)
    both = 5 + seed % 16
    only_a = 10 + (seed // 16) % 26
    only_b = 15 + (seed // 416) % 21
    a, b = both + only_a, both + only_b
    union = only_a + only_b + both
    probability = Fraction(union, 100)
    return _task(
        "overlapping-event-union", seed, profile,
        statement=(
            "В клубе 100 участников. Численности групп по занятиям: "
            f"шахматы — {a}, программирование — {b}, оба занятия — {both}. "
            "Участники обоих занятий включены в каждую из первых двух групп. "
            "Равновероятно выбирают одного участника. "
            "Найдите вероятность, что он занимается шахматами или программированием "
            "(возможно, и тем и другим)."
        ),
        answer=probability,
        hints=[
            "При сложении двух групп участники пересечения будут посчитаны дважды.",
            "Численность объединения равна |A| + |B| − |A ∩ B|.",
            f"Подходящих участников {a} + {b} − {both}; разделите это число на 100.",
        ],
        solution=[
            f"Число участников только шахмат: {only_a}; только программирования: {only_b}.",
            f"Добавляем группу обоих занятий: {only_a} + {only_b} + {both} = {union}.",
            f"P = {union}/100 = {decimal_text(probability)}.",
        ],
        formula=r"P(A\cup B)=P(A)+P(B)-P(A\cap B)",
        difficulty=2,
    )


def _total_probability_routing(seed: int, profile: ProfileSource) -> dict:
    _seed(seed)
    weight = Fraction(10 + seed % 81, 100)
    defect_a = Fraction(1 + (seed // 81) % 19, 100)
    defect_b = Fraction(20 + (seed // 1539) % 31, 100)
    first, second = weight * defect_a, (1 - weight) * defect_b
    probability = first + second
    return _task(
        "total-probability-routing", seed, profile,
        statement=(
            "В партии есть заготовки только со станков А и Б. Заготовку выбирают из всей партии "
            "равновероятно. В таблице приведены доли продукции станков и вероятность брака "
            "среди продукции каждого станка. Найдите вероятность выбрать бракованную заготовку."
        ),
        table={
            "headers": ["Станок", "Доля продукции в партии", "Вероятность брака на этом станке"],
            "rows": [
                ["А", decimal_text(weight), decimal_text(defect_a)],
                ["Б", decimal_text(1 - weight), decimal_text(defect_b)],
            ],
        },
        answer=probability,
        hints=[
            "Брак может прийти по двум несовместным путям: со станка А или со станка Б.",
            "Для каждого пути умножьте долю станка на вероятность брака именно на этом станке.",
            f"Сложите {decimal_text(weight)} · {decimal_text(defect_a)} и "
            f"{decimal_text(1 - weight)} · {decimal_text(defect_b)}.",
        ],
        solution=[
            "Происхождение заготовки разбивает все исходы на две несовместные группы.",
            f"Вероятности путей «А и брак» и «Б и брак» равны {decimal_text(first)} и "
            f"{decimal_text(second)}.",
            f"Полная вероятность брака равна их сумме: {decimal_text(probability)}.",
        ],
        formula=r"P(D)=P(A)P(D\mid A)+P(B)P(D\mid B)",
        difficulty=2,
    )


def _event_tree_exactly_one(seed: int, profile: ProfileSource) -> dict:
    _seed(seed)
    first = Fraction(1 + seed % 9, 10)
    after_success = Fraction(1 + seed % 4, 10)
    after_failure = Fraction(6 + (seed // 4) % 4, 10)
    sf = first * (1 - after_success)
    fs = (1 - first) * after_failure
    probability = sf + fs
    return _task(
        "event-tree-exactly-one", seed, profile,
        statement=(
            "Участник выполняет две попытки. Вероятность успеха первой равна "
            f"{decimal_text(first)}. "
            "Если первая успешна, условная вероятность успеха второй равна "
            f"{decimal_text(after_success)}; если первая неуспешна, она равна "
            f"{decimal_text(after_failure)}. Обе попытки выполняются в любом случае. "
            "Найдите вероятность ровно одной успешной попытки."
        ),
        answer=probability,
        hints=[
            "Нарисуйте два уровня дерева; вероятности второй попытки зависят от первой ветви.",
            "Подходят два пути: успех–неудача и неудача–успех. Вдоль пути вероятности умножаются.",
            f"Сложите {decimal_text(first)} · (1 − {decimal_text(after_success)}) и "
            f"(1 − {decimal_text(first)}) · {decimal_text(after_failure)}.",
        ],
        solution=[
            f"Путь успех–неудача имеет вероятность {decimal_text(sf)}.",
            f"Путь неудача–успех имеет вероятность {decimal_text(fs)}.",
            "Пути несовместны, поэтому вероятность ровно одного успеха равна "
            f"{decimal_text(probability)}.",
            "Общую вероятность успеха второй попытки нельзя подставлять вместо условных "
            "вероятностей ветвей.",
        ],
        formula=r"P(\text{ровно один})=p(1-q)+(1-p)r",
        difficulty=2,
    )


def _combinatorial_subset(seed: int, profile: ProfileSource) -> dict:
    _seed(seed)
    marked = (1, 3, 4, 6, 7, 9, 10, 12, 13, 15)[seed % 10]
    favorable, total = comb(marked, 2), comb(16, 2)
    probability = Fraction(favorable, total)
    return _task(
        "combinatorial-subset", seed, profile,
        statement=(
            f"Всего 16 различных карточек. Число отмеченных звёздочкой равно {marked}. "
            "Одновременно выбирают две разные карточки; все неупорядоченные пары равновероятны. "
            "Найдите вероятность, что обе выбранные карточки отмечены."
        ),
        answer=probability,
        hints=[
            "Порядок двух одновременно выбранных карточек не различается.",
            "Число пар из n различных объектов равно n(n − 1) / 2.",
            f"Всего пар 16 · 15 / 2; благоприятных — {marked} · ({marked} − 1) / 2.",
        ],
        solution=[
            f"Всего неупорядоченных пар: C(16, 2) = {total}.",
            f"Пар отмеченных карточек: C({marked}, 2) = {favorable}.",
            f"P = {favorable}/{total} = {decimal_text(probability)}.",
            "При единственной отмеченной карточке благоприятных пар нет, и вероятность равна нулю.",
        ],
        formula=r"P=\frac{\binom m2}{\binom N2}",
        difficulty=2,
    )


FAMILIES: tuple[Family, ...] = (
    Family("triangle-exterior-angle", 1, "Внешний угол треугольника", (
        "plane-angles", "plane-triangles", "plane-theorem-choice",
    ), _triangle_exterior_angle),
    Family("right-triangle-area", 1, "Площадь через неизвестный катет", (
        "plane-triangles", "plane-lengths", "plane-areas", "plane-theorem-choice",
    ), _right_triangle_area, supports_runtime=True),
    Family("trapezoid-area", 1, "Основания и высота трапеции", (
        "plane-quadrilaterals", "plane-areas",
    ), _trapezoid_area, supports_runtime=True),
    Family("cyclic-quadrilateral-angle", 1, "Противоположные углы на окружности", (
        "plane-angles", "plane-quadrilaterals", "plane-circles", "plane-theorem-choice",
    ), _cyclic_quadrilateral_angle),
    Family("similar-triangles-area", 1, "Как подобие меняет площадь", (
        "plane-triangles", "plane-similarity", "plane-areas", "plane-theorem-choice",
    ), _similar_triangles_area),
    Family("intersecting-chords", 1, "Отрезки пересекающихся хорд", (
        "plane-circles", "plane-lengths", "plane-theorem-choice",
    ), _intersecting_chords),
    Family("displacement-length", 2, "От координат точек к длине вектора", (
        "vector-coordinates", "vector-length",
    ), _displacement_length, supports_runtime=True),
    Family("vector-sum-length", 2, "Длина суммы векторов", (
        "vector-addition", "vector-length",
    ), _vector_sum_length),
    Family("vector-scaled-difference", 2, "Масштабирование и вычитание векторов", (
        "vector-subtraction", "vector-scaling",
    ), _vector_scaled_difference),
    Family("vector-dot-product", 2, "Скалярное произведение по координатам", (
        "vector-dot-product",
    ), _vector_dot_product, supports_runtime=True),
    Family("vector-angle", 2, "Угол между ненулевыми векторами", (
        "vector-angle", "vector-dot-product", "vector-length",
    ), _vector_angle),
    Family("right-prism-volume", 3, "Объём призмы с треугольным основанием", (
        "solid-prism", "solid-volume",
    ), _right_prism_volume, supports_runtime=True),
    Family("rectangular-box-surface", 3, "Все грани прямоугольного параллелепипеда", (
        "solid-parallelepiped", "solid-surface-area",
    ), _rectangular_box_surface, supports_runtime=True),
    Family("square-pyramid-volume", 3, "Площадь основания и высота пирамиды", (
        "solid-pyramid", "solid-volume",
    ), _square_pyramid_volume),
    Family("cylinder-volume-coefficient", 3, "Объём цилиндра без округления π", (
        "solid-cylinder", "solid-volume",
    ), _cylinder_volume_coefficient),
    Family("cone-surface-coefficient", 3, "Полная поверхность конуса", (
        "solid-cone", "solid-surface-area",
    ), _cone_surface_coefficient),
    Family("sphere-volume-coefficient", 3, "Коэффициент объёма шара", (
        "solid-sphere", "solid-volume",
    ), _sphere_volume_coefficient),
    Family("solid-similarity-volume", 3, "Куб коэффициента подобия", (
        "solid-prism", "solid-volume", "solid-ratios",
    ), _solid_similarity_volume),
    Family("urn-favorable-count", 4, "Что считать равновозможным исходом", (
        "probability-equiprobable", "probability-event",
    ), _urn_favorable_count),
    Family("integer-event-boundaries", 4, "Открытая и закрытая границы события", (
        "probability-equiprobable", "probability-event", "probability-event-boundaries",
    ), _integer_event_boundaries, supports_runtime=True),
    Family("complement-quality", 4, "Противоположное событие", (
        "probability-complement", "probability-event",
    ), _complement_quality, supports_runtime=True),
    Family("coin-pattern-enumeration", 4, "Последовательности бросков монеты", (
        "probability-equiprobable", "probability-event", "probability-event-boundaries",
    ), _coin_pattern_enumeration),
    Family("spinner-sector", 4, "Вероятность на круговом указателе", (
        "probability-event", "probability-event-boundaries",
    ), _spinner_sector),
    Family("independent-at-least-one", 5, "Хотя бы один из независимых успехов", (
        "probability-multiplication", "probability-independence",
    ), _independent_at_least_one, supports_runtime=True),
    Family("conditional-without-replacement", 5, "Условие меняет пространство исходов", (
        "probability-conditional",
    ), _conditional_without_replacement, supports_runtime=True),
    Family("overlapping-event-union", 5, "Объединение пересекающихся событий", (
        "probability-addition",
    ), _overlapping_event_union),
    Family("total-probability-routing", 5, "Полная вероятность по группам", (
        "probability-total", "probability-multiplication", "probability-addition",
    ), _total_probability_routing),
    Family("event-tree-exactly-one", 5, "Дерево зависимых попыток", (
        "probability-event-tree", "probability-conditional",
        "probability-multiplication", "probability-addition",
    ), _event_tree_exactly_one),
    Family("combinatorial-subset", 5, "Равновозможные неупорядоченные пары", (
        "probability-combinatorics",
    ), _combinatorial_subset),
)

_BY_ID = {family.id: family for family in FAMILIES}


def _section(heading: str, body: str, formula: str | None = None) -> dict:
    return {"heading": heading, "body": body, "formula": formula}


def build_lessons(profile: ProfileSource) -> list[dict]:
    """Return independent lesson copies; example values are authored separately."""
    lessons = []
    for family in FAMILIES:
        slot = next((item for item in profile.slots if item.number == family.slot), None)
        if slot is None or not set(family.skill_ids) <= {skill.id for skill in slot.skills}:
            raise ValueError("The profile does not contain this family's skills")
        lessons.append({
            "id": f"course-{family.id}", "title": family.title, "slot": family.slot,
            "minutes": 5, "skill_ids": list(family.skill_ids),
            "slot_id": slot.id, "review_status": "demo", "reviewed_by": None,
            **deepcopy(_LESSONS[family.id]),
            "family_ids": [family.id],
            "practice_task_ids": [f"course-{family.id}-{seed}" for seed in range(3)],
        })
    return lessons


_LESSONS: dict[str, dict] = {
    "triangle-exterior-angle": {
        "sections": [
            _section("Какой угол называют внешним", (
                "Внешний угол треугольника получается, когда одну сторону продолжают за вершину. "
                "В этом уроке рассматривается именно угол, смежный с внутренним, а не произвольный "
                "угол снаружи рисунка. Его стороны — одна сторона треугольника и продолжение "
                "другой. "
                "Внутренний и такой внешний угол образуют развёрнутый угол, поэтому их сумма "
                "равна ста восьмидесяти градусам. Прочитайте обозначение вершины: внешний угол "
                "при C связан со внутренним углом C. Это уточнение позволяет обойтись без масштаба "
                "рисунка и заранее понять, какие углы являются соседними, а какие — удалёнными."
            )),
            _section("Откуда берётся теорема", (
                "Обозначим внутренние углы буквами α, β и γ, а внешний при третьей вершине — δ. "
                "Для обычного невырожденного треугольника α + β + γ = 180°. Для смежных углов "
                "γ + δ = 180°. Вычтем первое равенство из второго: общий угол γ исчезнет, "
                "и останется δ = α + β. Таким образом, внешний угол равен сумме двух внутренних, "
                "не смежных с ним. Теорема применима к любому треугольнику на плоскости: "
                "равнобедренность и прямой угол для неё не требуются. Каждый из двух слагаемых "
                "положителен, значит внешний угол больше каждого удалённого внутреннего."
            ), r"\delta=\alpha+\beta"),
            _section("Выбор короткого решения", (
                "Если известны внешний угол и один удалённый внутренний, второй находится "
                "вычитанием. Можно сначала восстановить внутренний угол при внешнем, а затем "
                "воспользоваться суммой углов треугольника. Этот длинный путь полезен для "
                "проверки, "
                "потому что опирается на два знакомых правила. Не выбирайте теорему Пифагора: "
                "она связывает длины сторон прямоугольного треугольника, а здесь даны углы. "
                "Не делите внешний угол пополам без основания: удалённые углы могут быть "
                "неравными. Если бы условие сообщало равенство соответствующих сторон, "
                "тогда равенство противолежащих углов стало бы дополнительным аргументом."
            )),
            _section("Проверка существования и записи", (
                "Полученный внутренний угол должен быть строго между нулём и развёрнутым углом. "
                "Проверьте также третий внутренний угол и сумму всех трёх. Если разность внешнего "
                "и известного удалённого угла оказалась отрицательной, либо перепутаны вершины, "
                "либо исходные данные не описывают треугольник. Положительные углы с суммой "
                "сто восемьдесят градусов определяют возможную форму треугольника, но не его "
                "размер. "
                "Поэтому из такой задачи нельзя дополнительно извлечь длину стороны или площадь. "
                "В коротком ответе достаточно числового значения в градусах: знак градуса "
                "нужен в рассуждении, а единица уже указана в вопросе."
            )),
        ],
        "example": {
            "statement": (
                "В треугольнике угол A равен 47°, внешний угол при C равен 119°. Найдите B."
            ),
            "steps": [
                "Внешний угол при C равен сумме удалённых внутренних углов A и B.",
                "Поэтому B = 119° − 47° = 72°.",
                "Независимая проверка: внутренний C = 180° − 119° = 61°.",
                "Сумма 47° + 72° + 61° равна 180°; все три угла положительны.",
            ],
            "answer": "72",
        },
        "takeaway": "Сначала установите смежность. Внешний угол — сумма двух удалённых внутренних.",
    },
    "right-triangle-area": {
        "sections": [
            _section("Что известно и чего не хватает", (
                "Площадь треугольника равна половине произведения основания на проведённую к нему "
                "высоту. У прямоугольного треугольника два катета перпендикулярны, поэтому каждый "
                "из них может служить высотой к другому. Если условие даёт катет и гипотенузу, "
                "эти отрезки не образуют нужную пару основания и высоты. Сначала придётся найти "
                "второй катет. Определять гипотенузу следует по положению напротив прямого угла, "
                "а не по тому, какая сторона на картинке кажется наклонной. Она всегда длиннее "
                "каждого катета, что даёт полезную проверку исходных данных ещё до вычислений."
            )),
            _section("Точная длина по теореме Пифагора", (
                "Пусть c — гипотенуза, a — известный катет, b — неизвестный. Теорема Пифагора "
                "даёт a² + b² = c². Переносим квадрат известного катета: b² = c² − a². "
                "Длина положительна, поэтому берём положительный квадратный корень. Отрицательный "
                "корень уравнения не является длиной стороны. Извлекать корень отдельно из двух "
                "слагаемых нельзя: корень разности не равен разности корней. Иногда удобно "
                "разложить разность квадратов в произведение (c − a)(c + a), чтобы упростить "
                "устный счёт. Применение теоремы обосновано именно прямым углом, указанным в "
                "условии."
            ), r"b=\sqrt{c^2-a^2},\qquad S=\frac{ab}{2}"),
            _section("От длины к площади", (
                "Подставьте найденный катет в формулу площади только после проверки его значения. "
                "Если длины даны в сантиметрах, произведение двух длин измеряется в квадратных "
                "сантиметрах. Деление на два отражает то, что прямоугольный треугольник составляет "
                "половину прямоугольника с такими сторонами. Не используйте половину произведения "
                "катета и гипотенузы: соответствующий угол не прямой. Если промежуточный корень "
                "получился точным целым числом, сохраняйте его без десятичного приближения. "
                "В заданиях этой серии числа специально согласованы так, чтобы окончательная "
                "площадь записывалась точно, а не зависела от выбранной точности калькулятора."
            )),
            _section("Как проверить результат", (
                "Подставьте обе длины катетов обратно в равенство Пифагора. Затем представьте "
                "прямоугольник: его площадь должна быть ровно вдвое больше найденной. Эти две "
                "проверки ловят разные ошибки — неверный корень и пропущенное деление на два. "
                "Если гипотенуза не превосходит данный катет, положительного второго катета "
                "не существует; в корректном условии такой случай исключён. При увеличении "
                "всех сторон вдвое площадь возрастёт вчетверо, поэтому ответ, меняющийся "
                "линейно со стороной, подозрителен. Размеры на сопровождающей схеме помогают "
                "распознать вершины, но измерять изображение линейкой вместо вычисления не "
                "требуется."
            )),
        ],
        "example": {
            "statement": "Угол A прямой, AB = 15 см, BC = 17 см. Найдите площадь ABC в см².",
            "steps": [
                "BC — гипотенуза. Второй катет AC² = 17² − 15² = 289 − 225 = 64.",
                "Берём положительный корень: AC = 8 см.",
                "Катеты перпендикулярны, поэтому S = 15 · 8 / 2 = 60 см².",
                "Проверка: 15² + 8² = 17²; площадь прямоугольника со сторонами 15 и 8 равна 120 "
                "см².",
            ],
            "answer": "60",
        },
        "takeaway": (
            "Найдите недостающий катет по Пифагору, затем возьмите половину произведения катетов."
        ),
    },
    "trapezoid-area": {
        "sections": [
            _section("Основания отличаются от боковых сторон", (
                "У трапеции основаниями называют пару параллельных сторон. Высота — расстояние "
                "между прямыми, содержащими эти основания, то есть длина перпендикуляра к обеим "
                "прямым. Она не обязана совпадать с боковой стороной. В данном семействе известны "
                "оба основания и именно высота, поэтому форму наклонных сторон восстанавливать "
                "не нужно. Трапеции с одинаковыми основаниями и высотой могут выглядеть "
                "по-разному, но иметь одинаковую площадь. Это позволяет решать задачу по тексту "
                "даже без чертежа. Сначала проверьте, что все три длины выражены в одной единице, "
                "иначе формула смешает несопоставимые величины."
            )),
            _section("Почему появляется полусумма", (
                "Если приложить к трапеции её копию, повёрнутую на пол-оборота, получится "
                "параллелограмм. Его основание равно сумме оснований исходной трапеции, "
                "а высота остаётся прежней. Площадь параллелограмма равна произведению "
                "основания на высоту. Он состоит из двух равных трапеций, поэтому результат "
                "нужно разделить пополам. Так возникает формула S = (a + b)h / 2. "
                "Другой способ запомнить её: средняя линия трапеции равна полусумме оснований, "
                "а площадь равна произведению этой линии на высоту. Оба рассуждения описывают "
                "одну и ту же зависимость, а не два различных правила для разных трапеций."
            ), r"m=\frac{a+b}{2},\qquad S=mh"),
            _section("Последовательность вычислений", (
                "Сложите основания, разделите сумму на два и умножьте на высоту. При нечётной "
                "сумме оснований средняя линия может оказаться полуцелой: это нормальная длина, "
                "округлять её нельзя. Можно сначала умножить сумму на высоту и только затем "
                "делить, если так удобнее сокращать. Скобки существенны: запись a + bh / 2 "
                "не равна нужному выражению. Формула периметра здесь бесполезна: боковые "
                "стороны вообще не заданы, а вопрос касается площади. Отметьте квадратные "
                "единицы ответа; число сантиметров само по себе не описывает размер покрываемой "
                "поверхности и не должно подменять квадратные сантиметры."
            )),
            _section("Оценка без повторения арифметики", (
                "Средняя линия лежит между меньшим и большим основаниями. Поэтому площадь "
                "трапеции должна лежать между площадями прямоугольников с той же высотой "
                "и этими основаниями. Такая оценка помогает заметить пропущенные скобки "
                "или деление не на то число. Если основания сближаются по длине, формула "
                "переходит в привычное произведение основания на высоту прямоугольника "
                "или параллелограмма. Никакого специального условия равнобедренности для "
                "вычисления не требуется. Однако если вместо высоты была бы дана только "
                "наклонная сторона, потребовались бы дополнительные сведения: автоматически "
                "считать её высотой нельзя, даже когда рисунок кажется почти прямоугольным."
            )),
        ],
        "example": {
            "statement": (
                "Основания трапеции равны 7 см и 13 см, высота — 6 см. Найдите площадь в см²."
            ),
            "steps": [
                "Средняя линия равна (7 + 13) / 2 = 10 см.",
                "Умножаем среднюю линию на высоту: S = 10 · 6 = 60 см².",
                "Проверка оценкой: 7 · 6 = 42 и 13 · 6 = 78; число 60 лежит между ними.",
                "Равнобедренность не использовалась: площадь определили только основания и высота.",
            ],
            "answer": "60",
        },
        "takeaway": "Параллельные основания усредняют, затем умножают на перпендикулярную высоту.",
    },
    "cyclic-quadrilateral-angle": {
        "sections": [
            _section("Условие, которое выбирает теорему", (
                "Вписанный четырёхугольник имеет все четыре вершины на одной окружности. "
                "Это не то же самое, что четырёхугольник, описанный около окружности: "
                "во втором случае окружность касается его сторон. Здесь рассматривается "
                "выпуклый четырёхугольник с вершинами, перечисленными по порядку обхода. "
                "Углы при A и C противоположны, потому что между вершинами имеется ещё одна "
                "вершина в каждом направлении обхода. Порядок букв важен: угол BAD расположен "
                "при A, а угол BCD — при C. Середина трёхбуквенного обозначения всегда "
                "указывает вершину угла, независимо от того, как повернут рисунок."
            )),
            _section("Связь с вписанными углами", (
                "Угол BAD опирается на дугу BD, которая не содержит A. Угол BCD опирается "
                "на другую дугу с теми же концами, не содержащую C. Две дуги вместе "
                "образуют полную окружность. По теореме о вписанном угле каждый угол "
                "равен половине градусной меры своей дуги. Поэтому сумма двух углов "
                "равна половине полного оборота, то есть ста восьмидесяти градусам. "
                "Это свойство объясняет результат через окружность, а не через внешний "
                "вид четырёхугольника. Оно не утверждает, что противоположные углы равны: "
                "равенство возникло бы лишь в особом случае, когда оба угла прямые."
            ), r"\angle A+\angle C=180^\circ"),
            _section("Решение и границы применимости", (
                "После распознавания противоположных углов вычисление состоит из одного "
                "вычитания. Из развёрнутого угла вычитают известный и получают искомый. "
                "Знать радиус окружности, длины сторон и диагоналей не требуется. Для "
                "соседних углов такого равенства обычно нет: из одного угла вписанного "
                "четырёхугольника соседний определить нельзя. У произвольного выпуклого "
                "четырёхугольника известна только сумма всех четырёх углов, равная полному "
                "обороту. Поэтому применять равенство для противоположной пары без "
                "условия вписанности было бы логической ошибкой, даже если нарисованные "
                "вершины визуально напоминают точки некоторой окружности."
            )),
            _section("Самопроверка и обратное рассуждение", (
                "Если известный угол острый, противоположный обязан быть тупым, и наоборот. "
                "При прямом известном угле противоположный тоже прямой. Все внутренние "
                "углы выпуклого четырёхугольника строго меньше развёрнутого и больше нуля. "
                "Эти признаки позволяют быстро оценить ответ. Существует и обратный "
                "признак: если сумма противоположных углов выпуклого четырёхугольника "
                "равна ста восьмидесяти градусам, его можно вписать в окружность. "
                "В этой задаче доказывать обратный признак не нужно, но он помогает "
                "понять, почему условие о сумме связано именно с окружностью. "
                "Не переносите это правило на самопересекающуюся ломаную без отдельного анализа "
                "углов."
            )),
        ],
        "example": {
            "statement": (
                "Выпуклый четырёхугольник ABCD вписан в окружность; вершины идут по порядку. "
                "Угол BAD равен 113°. Найдите угол BCD в градусах."
            ),
            "steps": [
                "Углы BAD и BCD находятся при противоположных вершинах A и C.",
                "Их сумма равна 180°, поскольку четырёхугольник вписан в окружность.",
                "Угол BCD = 180° − 113° = 67°.",
                "Тупому углу 113° соответствует острый противоположный угол; сумма даёт 180°.",
            ],
            "answer": "67",
        },
        "takeaway": (
            "У вписанного выпуклого четырёхугольника противоположные углы дополняют друг друга "
            "до 180°."
        ),
    },
    "similar-triangles-area": {
        "sections": [
            _section("Как увидеть подобные треугольники", (
                "Отрезок, параллельный стороне треугольника, отсекает у противоположной "
                "вершины меньший треугольник той же формы. Пусть D лежит внутри AB, "
                "E — внутри AC, а DE параллельна BC. У треугольников ADE и ABC "
                "общий угол A; углы при D и B равны как соответственные при "
                "параллельных прямых. Двух равных углов достаточно для подобия. "
                "Сначала установите соответствие вершин A ↔ A, D ↔ B, E ↔ C. "
                "Тогда станет ясно, что AD соответствует AB, а не стороне BC "
                "или оставшемуся отрезку DB. Без этого шага легко составить неверное отношение."
            )),
            _section("Линейный коэффициент и квадрат", (
                "Коэффициент подобия малого треугольника большому равен k = AD / AB. "
                "Он показывает, во сколько раз уменьшилась каждая соответствующая "
                "длина, включая основание и высоту. Площадь равна половине произведения "
                "основания на высоту, поэтому при подобии она умножается на k дважды. "
                "Отсюда отношение площадей равно k². Умножение площади только на k "
                "смешивает линейные и квадратные величины. Периметры действительно "
                "относятся как k, но площади — иначе. Доказательство через две длины "
                "надёжнее механического запоминания показателя степени и помогает затем "
                "различать масштаб длины, площади и объёма."
            ), r"k=\frac{AD}{AB},\qquad S_{ADE}=k^2S_{ABC}"),
            _section("Как считать без округлений", (
                "Отношение сторон может быть обыкновенной дробью с бесконечной десятичной "
                "записью. Это не повод округлять: сохраните числитель и знаменатель, "
                "возведите оба в квадрат и сократите с известной площадью. Итог "
                "может оказаться целым или конечным десятичным числом, хотя сам "
                "коэффициент им не был. Если ищется большая площадь по малой, "
                "нужно делить на k², а не умножать. Удобно подписывать словами "
                "числитель и знаменатель отношения. Не складывайте длины AD и AB: "
                "меньший отрезок уже входит в больший. Если дан DB, сначала "
                "восстановите AB или AD из правильного равенства отрезков."
            )),
            _section("Проверяем геометрический смысл", (
                "В этой конфигурации точки D и E внутренние, поэтому коэффициент "
                "строго между нулём и единицей. Его квадрат ещё меньше, следовательно "
                "малая площадь должна быть меньше большой. При половинном линейном "
                "размере получается четверть площади, что удобно представлять мысленно. "
                "Для существования фигуры достаточно невырожденного большого треугольника "
                "и внутренней точки D: параллель через неё пересечёт AC во внутренней "
                "точке E. Размер угла A восстанавливать не нужно. Урок касается "
                "именно подобных треугольников; одинаковая высота или равные площади "
                "сами по себе ещё не гарантируют подобия и не разрешают применять квадрат "
                "отношения сторон."
            )),
        ],
        "example": {
            "statement": (
                "В треугольнике ABC точки D и E лежат внутри сторон AB и AC, DE ∥ BC. "
                "AB = 15 см, AD = 9 см, площадь ABC равна 125 см². Найдите площадь ADE в см²."
            ),
            "steps": [
                "По двум углам треугольники ADE и ABC подобны; D соответствует B.",
                "Коэффициент малого к большому: k = 9/15 = 3/5.",
                "Отношение площадей равно 9/25. Поэтому S(ADE) = 125 · 9/25 = 45 см².",
                "Проверка: 45 меньше 125; применён квадрат отношения, а не отношение длин.",
            ],
            "answer": "45",
        },
        "takeaway": (
            "Сопоставьте стороны, найдите линейный коэффициент и возведите его в квадрат для "
            "площадей."
        ),
    },
    "intersecting-chords": {
        "sections": [
            _section("Четыре отрезка у одной точки", (
                "Хорда соединяет две точки окружности. Если две хорды пересекаются "
                "внутри круга, общая точка делит каждую на два положительных отрезка. "
                "Для хорд AB и CD с точкой пересечения E это пары AE, EB "
                "и CE, ED. Важно не спутать отдельные части с полными длинами "
                "AB и CD. В данном семействе известны три части, требуется четвёртая. "
                "Расположение хорд под прямым углом не предполагается. На рисунке "
                "они могут пересекаться как угодно; основная связь определяется "
                "тем, что четыре конца лежат на одной окружности и общая точка внутренняя."
            )),
            _section("Почему произведения совпадают", (
                "Соединим A с D и C с B. Треугольники AED и CEB "
                "имеют равные вертикальные углы при E. Угол ADE равен углу "
                "CBE: это вписанные углы, опирающиеся на одну дугу AC. "
                "Следовательно, треугольники подобны. Соответствие сторон даёт "
                "AE / CE = ED / EB. Перемножив крест-накрест, получаем "
                "AE · EB = CE · ED. У каждой хорды перемножаются именно "
                "две её части. Это полезный способ восстановить формулу, если "
                "она забыта: равенство длин или сумм для произвольных хорд "
                "не следует из подобия и в общем случае неверно."
            ), r"AE\cdot EB=CE\cdot ED"),
            _section("Выражаем неизвестный отрезок", (
                "Разделите произведение двух частей известной хорды на известную "
                "часть другой. Делитель положителен, поскольку E лежит строго "
                "внутри хорды. Все длины предварительно переведите в одинаковые "
                "единицы. Произведение длин измеряется в квадратных сантиметрах, "
                "а после деления снова получится длина в сантиметрах. "
                "Не заменяйте CE длиной всей хорды CD. Если условие давало "
                "бы целую хорду и одну часть, недостающую часть сначала "
                "нужно было бы найти вычитанием. Для секущих из внешней "
                "точки действует родственное правило, но там перемножаются "
                "внешняя часть и полная секущая; переносить обозначения без проверки нельзя."
            )),
            _section("Контроль результата и области теоремы", (
                "Умножьте найденный ED на CE и сравните с первым произведением. "
                "Это простая обратная проверка, особенно полезная при сокращении "
                "дробей. Все четыре отрезка должны быть положительны. Само "
                "равенство не означает, что хорды имеют одинаковую длину: "
                "разные пары чисел могут иметь одно произведение и разные суммы. "
                "Ни радиус окружности, ни угол пересечения для требуемого "
                "отрезка знать не надо. Если точка находится вне окружности "
                "или один конец не принадлежит ей, сначала выберите подходящую "
                "теорему для новой конфигурации. Название «пересекающиеся отрезки» "
                "само по себе ещё не даёт права применять свойство хорд."
            )),
        ],
        "example": {
            "statement": (
                "Хорды AB и CD пересекаются внутри окружности в E. AE = 9 см, EB = 4 см, CE = 6 "
                "см. Найдите ED."
            ),
            "steps": [
                "Применяем равенство произведений частей хорд: 9 · 4 = 6 · ED.",
                "Делим обе части на положительное число 6: ED = 36/6 = 6 см.",
                "Проверка: 9 · 4 = 36 и 6 · 6 = 36 квадратных сантиметров.",
                "Полные хорды здесь равны 13 и 12 см; равенства их длин теорема не требует.",
            ],
            "answer": "6",
        },
        "takeaway": (
            "Перемножайте части одной хорды; неизвестная часть равна общему произведению, "
            "делённому на соседнюю."
        ),
    },
}

_LESSONS.update({
    "displacement-length": {
        "sections": [
            _section("Вектор описывает перемещение", (
                "Точка задаёт положение, а вектор — перемещение от начала к концу. "
                "Вектор AB направлен из A в B. Его первая координата показывает, "
                "на сколько изменяется горизонтальная координата, вторая — вертикальная. "
                "Поэтому из каждой координаты конца вычитают соответствующую координату "
                "начала. Если движение идёт влево или вниз, нужная разность отрицательна. "
                "Это не ошибка и не отрицательная длина: знак относится к направлению "
                "проекции. При переносе обеих точек на один и тот же вектор разности "
                "не меняются. Значит, длина зависит от взаимного расположения точек, "
                "а не от выбранного положения начала координат."
            )),
            _section("Длина как гипотенуза", (
                "В прямоугольной декартовой системе координат горизонтальная и вертикальная "
                "проекции перпендикулярны. Вместе с отрезком AB они образуют "
                "прямоугольный треугольник, поэтому работает теорема Пифагора. "
                "Квадрат длины равен сумме квадратов двух координат вектора. "
                "Квадрат отрицательного числа положителен, поэтому направления "
                "проекций не меняют модуль. Длина получается как неотрицательный "
                "квадратный корень. Если обе координаты нулевые, точки совпадают "
                "и длина равна нулю. Для любых других координат сумма квадратов "
                "строго положительна. Формула предполагает одинаковый единичный "
                "масштаб по осям; на растянутом рисунке нельзя просто измерять диагональ."
            ), r"\overrightarrow{AB}=(x_B-x_A;y_B-y_A),\quad |AB|=\sqrt{(x_B-x_A)^2+(y_B-y_A)^2}"),
            _section("Рабочая последовательность", (
                "Выпишите две разности в отдельной строке и только потом возводите "
                "их в квадрат. Такая запись уменьшает риск перепутать координаты "
                "разных точек. Особенно внимательно раскрывайте вычитание отрицательного "
                "числа: выражение x_B − (−c) превращается в x_B + c. "
                "Складывать абсолютные значения проекций нельзя: это длина пути "
                "с поворотом вдоль осей, а не прямого перемещения. Квадратный "
                "корень берут от всей суммы квадратов, а не отдельно от каждого "
                "слагаемого. Если под корнем полный квадрат, запишите точное "
                "целое число; никакая дополнительная точность округления здесь не нужна."
            )),
            _section("Проверки направления и масштаба", (
                "Поменяйте начало и конец местами: обе координаты вектора сменят "
                "знак, но сумма их квадратов останется прежней. Это соответствует "
                "геометрии: отрезок имеет одну длину в обоих направлениях. "
                "Искомая длина не может быть меньше модуля любой из проекций. "
                "Она также не превосходит суммы модулей проекций. Эти оценки "
                "помогают обнаружить арифметическую ошибку до подстановки назад. "
                "Ответ измеряется в единицах длины той системы координат, "
                "в которой заданы точки. Если вопрос касается координат самого "
                "вектора, одного модуля недостаточно; в этом уроке координаты "
                "служат обязательным промежуточным шагом к расстоянию между двумя точками."
            )),
        ],
        "example": {
            "statement": "Даны A(−2; 5) и B(10; −4). Найдите длину вектора AB.",
            "steps": [
                "Вычитаем начало из конца: AB = (10 − (−2); −4 − 5) = (12; −9).",
                "Квадрат длины равен 12² + (−9)² = 144 + 81 = 225.",
                "Длина — неотрицательный корень: |AB| = 15.",
                "Число 15 не меньше обеих проекций по модулю и меньше их суммы 21.",
            ],
            "answer": "15",
        },
        "takeaway": (
            "Конец минус начало даёт координаты перемещения; корень из суммы их квадратов даёт "
            "длину."
        ),
    },
    "vector-sum-length": {
        "sections": [
            _section("Сумма последовательных перемещений", (
                "Сложение векторов описывает результат двух последовательных перемещений. "
                "Можно перенести второй вектор так, чтобы его начало совпало "
                "с концом первого. Сумма направлена от начала первого к концу "
                "перенесённого второго: это правило треугольника. В координатах "
                "горизонтальные изменения складываются с горизонтальными, "
                "вертикальные — с вертикальными. Перенос вектора без поворота "
                "не меняет его координаты, поэтому положение нарисованных "
                "стрелок не влияет на результат. Не следует считать, что два "
                "вектора обязаны иметь общее начало уже в условии: свободные "
                "векторы складываются по одинаковому правилу независимо от места изображения."
            )),
            _section("Две операции вместо одной", (
                "Вопрос о длине суммы требует сначала получить саму сумму "
                "как пару координат, а затем найти модуль этой пары. "
                "Если a = (a_x; a_y), b = (b_x; b_y), то "
                "a + b = (a_x + b_x; a_y + b_y). Длина определяется "
                "теоремой Пифагора в прямоугольной системе координат. "
                "Нельзя заменить эти две операции сложением длин исходных "
                "векторов. Такое сложение считает длину ломаной, которая "
                "в общем случае больше расстояния между её концами. "
                "Равенство длин возникает лишь при сонаправленных векторах "
                "или при нулевом слагаемом, а произвольные координаты этого не гарантируют."
            ), r"|a+b|=\sqrt{(a_x+b_x)^2+(a_y+b_y)^2}"),
            _section("Знаки отражают компенсацию", (
                "Если две горизонтальные координаты имеют разные знаки, "
                "соответствующие перемещения частично компенсируются. "
                "То же происходит по вертикали. Поэтому отрицательные "
                "координаты надо сохранять до сложения, а не заменять "
                "их модулями. После сложения квадрат каждой итоговой "
                "координаты уже будет неотрицательным. Полезно группировать "
                "вычисления в две отдельные строки, чтобы случайно не "
                "сложить первую координату одного вектора со второй другого. "
                "Если сумма имеет одну нулевую координату, её длина "
                "равна модулю оставшейся. Если нулевые обе, перемещения "
                "полностью компенсировались, и длина суммы равна нулю: такой результат допустим."
            )),
            _section("Как оценить ответ", (
                "В мысленной схеме результирующий вектор замыкает ломаную. "
                "Он не может быть длиннее суммы длин двух её звеньев. "
                "При этом его длина не меньше разности длин исходных "
                "векторов по модулю. Эти неравенства треугольника помогают "
                "проверить порядок величины, но не заменяют точного "
                "вычисления по координатам. Ещё один контроль — поменять "
                "векторы местами: координатная сумма и её модуль останутся "
                "такими же. В задачах этой серии корень извлекается точно. "
                "Если собственное вычисление дало неудобный корень, сначала "
                "проверьте сложение со знаками, а не переходите к произвольному округлению "
                "числового ответа."
            )),
        ],
        "example": {
            "statement": "a = (7; −3), b = (−2; 15). Найдите длину a + b.",
            "steps": [
                "Складываем соответствующие координаты: a + b = (7 − 2; −3 + 15) = (5; 12).",
                "Длина суммы равна √(5² + 12²) = √169 = 13.",
                "Отрицательная первая координата b уменьшила горизонтальное перемещение.",
                "Число 13 относится к результирующему вектору; длины a и b по отдельности не "
                "складывались.",
            ],
            "answer": "13",
        },
        "takeaway": (
            "Сначала сложите координаты с их знаками. Только затем находите модуль "
            "результирующего вектора."
        ),
    },
    "vector-scaled-difference": {
        "sections": [
            _section("Умножение меняет каждую координату", (
                "Умножить вектор на число означает умножить на это число "
                "каждую его координату. При положительном множителе "
                "направление сохраняется, при отрицательном меняется "
                "на противоположное. Длина умножается на модуль числа, "
                "а при нулевом множителе получается нулевой вектор. "
                "Если b = (b_x; b_y), то kb = (kb_x; kb_y). "
                "Нельзя умножить только одну координату: это меняет "
                "само правило преобразования и обычно поворачивает "
                "вектор. Здесь масштабирование выполняется перед вычитанием, "
                "поскольку в выражении a − kb произведение образует одно целое слагаемое."
            )),
            _section("Вычитание как сложение с противоположным", (
                "Разность a − c можно понимать как сумму a и "
                "противоположного вектора −c. Поэтому обе координаты "
                "c вычитаются из соответствующих координат a. "
                "В выражении a − kb это даёт пару "
                "(a_x − kb_x; a_y − kb_y). Скобки помогают "
                "видеть, что минус относится ко всему вектору, "
                "а не только к первой координате. При вычитании "
                "отрицательного произведения знак меняется на плюс. "
                "Обычные правила работы с отрицательными числами "
                "действуют в каждой координате отдельно; никакого "
                "дополнительного геометрического правила для знаков векторная запись не вводит."
            ), r"a-kb=(a_x-kb_x;\ a_y-kb_y)"),
            _section("Что именно требуется в ответе", (
                "Если спрашивается только вторая координата, окончательный "
                "ответ — одно число, а не вектор и не его длина. "
                "Вторая координата может быть отрицательной, нулевой "
                "или положительной. Брать её модуль не нужно. "
                "Вычисление первой координаты можно оставить для "
                "контроля, но оно не обязательно для нахождения "
                "второй. В учебном разборе полезно один раз "
                "выписать весь вектор kb, затем весь результат: "
                "так легче увидеть распределение множителя и "
                "знака вычитания. Когда правило уверенно усвоено, "
                "можно сразу подставлять в формулу a_y − kb_y, сохраняя точный порядок действий."
            )),
            _section("Обратная проверка", (
                "Обозначьте найденную разность буквой w. Тогда должно "
                "выполняться w + kb = a. Проверить это можно "
                "по одной интересующей координате или по обеим. "
                "Так обнаруживаются ошибки в знаках и случаи, "
                "когда множитель по ошибке применили к a. "
                "Вычитание векторов не перестановочно: kb − a "
                "даёт противоположный результат. Это отличается "
                "от сложения и заслуживает отдельного внимания. "
                "Также a − kb не равно k(a − b), "
                "если нет специальных значений множителя или "
                "векторов: раскрытие последних скобок даёт ka − kb. "
                "Сравнение этих выражений помогает понять, почему нельзя выносить k без основания."
            )),
        ],
        "example": {
            "statement": "a = (5; 7), b = (−2; 3), k = 4. Найдите вторую координату a − kb.",
            "steps": [
                "Умножаем обе координаты b на четыре: kb = (−8; 12).",
                "Вычитаем: a − kb = (5 − (−8); 7 − 12) = (13; −5).",
                "Вторая координата равна −5. Не заменяем её модулем, потому что не ищем длину.",
                "Обратная проверка второй координаты: −5 + 12 = 7, как у вектора a.",
            ],
            "answer": "-5",
        },
        "takeaway": (
            "Сначала умножьте обе координаты b на k; затем вычтите. Координата сохраняет свой "
            "знак."
        ),
    },
    "vector-dot-product": {
        "sections": [
            _section("Произведение, результат которого — число", (
                "Скалярное произведение двух векторов обозначают точкой. "
                "В отличие от суммы или разности, его результатом "
                "является одно число. В прямоугольной декартовой "
                "системе с единичным масштабом оно вычисляется "
                "как сумма произведений соответствующих координат. "
                "Первая координата первого вектора умножается "
                "на первую второго, вторая — на вторую. "
                "Перекрёстные произведения здесь не участвуют. "
                "Значение может быть положительным, нулевым "
                "или отрицательным. Это существенно отличает "
                "скалярное произведение от длины: отрицательный результат сам по себе не "
                "означает ошибки."
            )),
            _section("Связь с геометрическим смыслом", (
                "Геометрическое определение связывает произведение "
                "с длинами векторов и косинусом угла между ними. "
                "Если ненулевые векторы направлены примерно "
                "в одну сторону и угол острый, произведение "
                "положительно. При прямом угле оно равно "
                "нулю, при тупом — отрицательно. Формула "
                "по координатам позволяет вычислить его "
                "без нахождения самого угла. В этом уроке "
                "именно координатный способ является рабочим: "
                "угол не задан и дополнительно определять "
                "его не требуется. При этом геометрический смысл полезен для проверки знака "
                "и помогает не путать скалярное произведение с произведением длин."
            ), r"a\cdot b=a_xb_x+a_yb_y"),
            _section("Порядок вычисления со знаками", (
                "Сначала запишите два произведения в скобках "
                "и найдите каждое отдельно. Затем сложите "
                "результаты с их знаками. Такой порядок "
                "защищает от случайной замены сложения "
                "вычитанием или умножения не тех координат. "
                "Произведение двух отрицательных координат "
                "положительно; произведение отрицательной "
                "и положительной — отрицательно. Не надо "
                "перед вычислением заменять координаты модулями: "
                "так исчезнет информация о взаимном направлении. "
                "Не извлекайте квадратный корень из полученной суммы. "
                "Корень появляется в формуле длины, а здесь операция завершена уже после "
                "сложения двух произведений, даже если итоговое число выглядит непривычно."
            )),
            _section("Полезные частные случаи", (
                "Если один вектор нулевой, произведение равно "
                "нулю при любом втором векторе. Поэтому "
                "из нулевого произведения можно заключить "
                "о перпендикулярности только после проверки "
                "ненулевых длин. Произведение вектора на "
                "самого себя равно квадрату его длины "
                "и не бывает отрицательным. При перестановке "
                "двух векторов результат не меняется: "
                "обычное умножение координат перестановочно. "
                "Эти факты дают быстрые способы проверить "
                "вычисление в подходящих случаях. Если нужно "
                "проверить произвольный результат другим способом, можно использовать "
                "равенство 2(a · b) = |a + b|² − |a|² − |b|², "
                "но оно требует больше арифметики и не обязательно для короткого ответа."
            )),
        ],
        "example": {
            "statement": "a = (−4; 6), b = (3; 5). Найдите a · b.",
            "steps": [
                "Произведение первых координат равно (−4) · 3 = −12.",
                "Произведение вторых координат равно 6 · 5 = 30.",
                "Складываем: a · b = −12 + 30 = 18.",
                "Результат — число 18, а не пара (−12; 30). Положительный знак согласуется с "
                "острым углом.",
            ],
            "answer": "18",
        },
        "takeaway": (
            "Скалярное произведение — сумма попарных произведений координат, без корня и без "
            "взятия модулей."
        ),
    },
    "vector-angle": {
        "sections": [
            _section("Какой угол ищется", (
                "Угол между ненулевыми векторами выбирают "
                "от нуля до развёрнутого угла включительно. "
                "Для сравнения их можно параллельно перенести "
                "к общему началу. Направление каждого вектора "
                "сохраняют: заменить стрелку противоположной "
                "означает изменить угол. У нулевого вектора "
                "направления нет, поэтому угол с ним "
                "в этой модели не определён. Перед применением "
                "формулы обязательно убедитесь, что суммы "
                "квадратов координат обоих векторов положительны. "
                "На рисунке меньший геометрический угол между прямыми может отличаться "
                "от угла между направленными векторами: противоположно направленные векторы дают "
                "180°."
            )),
            _section("Формула соединяет три вычисления", (
                "Скалярное произведение равно произведению "
                "длин на косинус угла. Деление на "
                "положительное произведение длин выражает "
                "косинус. По координатам сначала найдите "
                "числитель — сумму двух попарных произведений. "
                "Затем вычислите квадраты длин и "
                "сохраните корни точно. Корень из "
                "произведения положительных чисел можно "
                "упрощать, выделяя полные квадраты. "
                "Округлять длины заранее не следует: "
                "это может превратить точное табличное значение косинуса в близкую, "
                "но неудобную дробь. В заданиях этой серии конечный угол имеет "
                "точное значение в градусах, хотя промежуточные длины иногда иррациональны."
            ), r"\cos\varphi=\frac{a_xb_x+a_yb_y}{\sqrt{a_x^2+a_y^2}\sqrt{b_x^2+b_y^2}}"),
            _section("От косинуса к углу", (
                "После сокращения сопоставьте результат "
                "с известными значениями косинуса. "
                "Единица соответствует нулевому углу, "
                "ноль — прямому, минус единица — "
                "развёрнутому. Значения √2/2 и "
                "−√2/2 соответствуют 45° и 135°. "
                "Знак произведения позволяет заранее "
                "понять, в какой половине промежутка "
                "лежит угол. Нельзя отбросить минус "
                "перед косинусом: острый и тупой "
                "углы тогда перепутаются. На промежутке от нуля до ста "
                "восьмидесяти градусов косинус принимает каждое своё значение "
                "один раз, поэтому искомый угол определяется однозначно без выбора "
                "между несколькими полными оборотами или отрицательными направлениями отсчёта. "
                "Если пользуетесь таблицей, ищите именно косинус, а не синус того же угла: "
                "для некоторых значений они различаются."
            )),
            _section("Проверки и быстрые случаи", (
                "Косинус обязан лежать между минус "
                "единицей и единицей. Выход за "
                "эти границы означает вычислительную "
                "ошибку, часто связанную с забытым "
                "корнем в знаменателе. Если второй "
                "вектор является положительным кратным "
                "первого, угол нулевой; при отрицательном "
                "кратном он развёрнутый. Если произведение "
                "равно нулю и оба вектора ненулевые, "
                "угол прямой. Эти признаки полезны как "
                "независимый контроль формулы. Для произвольного угла не используйте "
                "только знак произведения: он различает острый и тупой случаи, "
                "но не даёт точного численного значения. Ответ записывайте "
                "в градусах согласно вопросу, не подменяя его найденным косинусом."
            )),
        ],
        "example": {
            "statement": "a = (3; 1), b = (2; 4). Найдите угол между ними в градусах.",
            "steps": [
                "a · b = 3 · 2 + 1 · 4 = 10; обе длины ненулевые.",
                "|a| = √10, |b| = √20, их произведение равно √200 = 10√2.",
                "cos φ = 10/(10√2) = √2/2, значит φ = 45°.",
                "Произведение положительно, поэтому острый угол согласуется со знаком числителя.",
            ],
            "answer": "45",
        },
        "takeaway": (
            "Проверьте ненулевые длины, найдите точный косинус и восстановите угол на промежутке "
            "0°–180°."
        ),
    },
})

_LESSONS.update({
    "right-prism-volume": {
        "sections": [
            _section("Основание и высота относятся к разным фигурам", (
                "У призмы два равных параллельных основания, "
                "а боковые грани соединяют соответствующие "
                "стороны этих оснований. В данном семействе "
                "основание — прямоугольный треугольник. "
                "Его катеты лежат в одной плоскости "
                "и нужны для вычисления площади основания. "
                "Высота призмы — расстояние между "
                "плоскостями оснований, перпендикулярное "
                "им. Она не является высотой "
                "треугольника основания. У прямой "
                "призмы боковые рёбра перпендикулярны основаниям, поэтому их длина "
                "совпадает с высотой. Слово «прямая» описывает расположение "
                "боковых рёбер, а слово «прямоугольный» — форму треугольника в основании."
            )),
            _section("Объём собирается из одинаковых сечений", (
                "Для призмы площадь сечения, параллельного "
                "основанию, одинакова на любой высоте. "
                "Поэтому объём равен произведению "
                "площади основания на расстояние "
                "между основаниями. Это пространственный "
                "аналог вычисления площади прямоугольника, "
                "только вместо длины основания "
                "теперь используется его площадь. "
                "У прямоугольного треугольника площадь "
                "равна половине произведения катетов. "
                "Подставляя её в формулу призмы, получаем V = abh / 2. "
                "Гипотенузу основания находить не нужно: катеты уже образуют "
                "перпендикулярную пару, достаточную для площади. Это позволяет "
                "обойти лишний квадратный корень и сохранить вычисление коротким."
            ), r"S_{\text{осн}}=\frac{ab}{2},\qquad V=S_{\text{осн}}h"),
            _section("Размерности помогают выбрать действие", (
                "Сначала получите площадь в квадратных "
                "сантиметрах, затем умножьте её "
                "на высоту в сантиметрах. "
                "Результат измеряется в кубических "
                "сантиметрах. Если вместо этого "
                "получились квадратные единицы, "
                "какое-то линейное измерение "
                "не было учтено. Не умножайте "
                "сумму сторон основания на "
                "высоту: такое выражение относится "
                "к боковой поверхности прямой призмы, а не к объёму. "
                "Не делите объём на три: этот коэффициент появляется "
                "у пирамиды, сечения которой сужаются к вершине. "
                "Здесь все параллельные сечения сохраняют площадь, "
                "поэтому после вычисления треугольного основания нового деления не возникает."
            )),
            _section("Контроль и пределы модели", (
                "Все размеры должны быть положительными. "
                "Два положительных катета всегда "
                "задают существующий прямоугольный "
                "треугольник, а положительная высота "
                "задаёт призму над ним. "
                "Можно достроить основание "
                "до прямоугольника: соответствующий "
                "прямоугольный параллелепипед имеет "
                "вдвое больший объём. Такая "
                "проверка ловит пропущенное деление "
                "на два. При удвоении только высоты объём удваивается; "
                "при удвоении всех трёх линейных размеров возрастает "
                "восемь раз. Если призма была бы наклонной, "
                "формула через перпендикулярную высоту сохранилась бы, "
                "но длину бокового ребра нельзя было бы автоматически считать этой высотой."
            )),
        ],
        "example": {
            "statement": (
                "В основании прямой призмы катеты 5 см и 8 см. Высота призмы 9 см. Найдите объём "
                "в см³."
            ),
            "steps": [
                "Площадь треугольного основания равна 5 · 8 / 2 = 20 см².",
                "Объём призмы V = 20 · 9 = 180 см³.",
                "У достроенного параллелепипеда объём 5 · 8 · 9 = 360 см³, вдвое больше.",
                "Гипотенуза основания не понадобилась: объём определён площадью и высотой.",
            ],
            "answer": "180",
        },
        "takeaway": (
            "Отдельно найдите площадь треугольного основания и умножьте её на высоту всей призмы."
        ),
    },
    "rectangular-box-surface": {
        "sections": [
            _section("Полная поверхность означает все шесть граней", (
                "Прямоугольный параллелепипед задаётся тремя "
                "положительными измерениями: длиной, "
                "шириной и высотой. Его грани "
                "являются прямоугольниками. Если "
                "спрашивается полная поверхность, "
                "нужно учесть все шесть "
                "граней, включая верхнюю и "
                "нижнюю. Слово «коробка» в "
                "бытовом описании иногда заставляет "
                "вообразить открытую крышку, "
                "но математический параллелепипед замкнут, если условие явно "
                "не исключает грань. В этой серии прямо сказано "
                "«включая все грани». Это уточнение определяет модель "
                "и защищает от ошибочного перехода к площади боковой поверхности."
            )),
            _section("Три вида прямоугольников", (
                "Обозначим измерения a, b и c. "
                "Две противоположные грани "
                "имеют размеры a и b, "
                "ещё две — a и c, "
                "последние две — b и c. "
                "Площадь каждой пары вдвое "
                "больше площади одного "
                "прямоугольника. Складывая пары, "
                "получаем S = 2ab + 2ac + 2bc. "
                "Общий множитель два можно "
                "вынести за скобки. Это не формула объёма: произведение "
                "abc характеризует внутреннее пространство, тогда как "
                "сумма попарных произведений характеризует оболочку. "
                "Полезно мысленно развернуть грани на плоскость, "
                "чтобы увидеть все шесть прямоугольников и не пропустить ни одну пару."
            ), r"S=2(ab+ac+bc)"),
            _section("Вычисление и единицы", (
                "Выпишите три попарных произведения "
                "отдельно. Затем сложите их "
                "и удвойте сумму. Такой "
                "порядок лучше, чем пытаться "
                "сразу перемножить или сложить "
                "все числа условия. Размеры "
                "должны быть выражены в "
                "одинаковых единицах: если "
                "одна сторона дана в "
                "метрах, сначала приведите "
                "её к сантиметрам или остальные к метрам. После "
                "перемножения двух длин единицы становятся квадратными. "
                "Не переносите автоматически единицу длины из "
                "условия в ответ. Площадь не может быть "
                "отрицательной, потому что все три произведения положительны. "
                "Совпадение двух измерений просто делает некоторые грани одинаковыми "
                "и не меняет общего способа подсчёта."
            )),
            _section("Как проверить подсчёт граней", (
                "Перестановка названий длины, ширины "
                "и высоты не должна менять "
                "ответ: поверхность одного "
                "тела не зависит от "
                "того, как его повернули. "
                "Формула действительно симметрична "
                "относительно трёх измерений. "
                "Если все они равны a, "
                "получится куб с шестью "
                "квадратными гранями, то "
                "есть S = 6a². Это удобный частный случай для "
                "проверки формулы. При удвоении всех размеров "
                "каждая грань увеличится вчетверо и вся "
                "поверхность тоже. При удвоении лишь высоты "
                "основания сохраняют площадь, поэтому вся поверхность "
                "не обязана удваиваться. Эта разница помогает отделить площадь от объёма."
            )),
        ],
        "example": {
            "statement": (
                "Измерения прямоугольного параллелепипеда: 4 см, 6 см, 9 см. Найдите полную "
                "поверхность в см²."
            ),
            "steps": [
                "Площади трёх видов граней равны 4 · 6 = 24, 4 · 9 = 36 и 6 · 9 = 54 см².",
                "Каждая грань имеет равную противоположную: S = 2(24 + 36 + 54).",
                "Сумма в скобках равна 114, поэтому полная поверхность равна 228 см².",
                "Все шесть граней учтены; произведение 4 · 6 · 9 дало бы другую величину — объём.",
            ],
            "answer": "228",
        },
        "takeaway": (
            "Посчитайте три попарные площади и удвойте их сумму: противоположные грани равны."
        ),
    },
    "square-pyramid-volume": {
        "sections": [
            _section("Высота не обязана быть ребром", (
                "Пирамида состоит из основания "
                "и треугольных боковых граней, "
                "которые сходятся в одной "
                "вершине. Высота пирамиды — "
                "перпендикуляр из этой вершины "
                "к плоскости основания. "
                "Он обычно не совпадает "
                "ни с боковым ребром, "
                "ни с высотой боковой "
                "грани. В нашем условии "
                "длина перпендикуляра указана явно, поэтому можно сразу "
                "применять формулу объёма. Основание является квадратом, "
                "но это само по себе не означает, что вершина "
                "расположена над его центром. Для объёма такое "
                "расположение несущественно, если известны площадь основания и перпендикулярная "
                "высота."
            )),
            _section("Почему объём меньше объёма призмы", (
                "У пирамиды сечения, параллельные "
                "основанию, уменьшаются при "
                "приближении к вершине. "
                "Поэтому нельзя умножить "
                "площадь основания на "
                "высоту и считать работу "
                "законченной: так получится "
                "объём призмы с теми "
                "же основанием и высотой. "
                "Теорема об объёме пирамиды "
                "даёт ровно треть этого произведения. Формула "
                "применяется к любой пирамиде, не только "
                "правильной. Для квадрата со стороной a "
                "площадь основания равна a², поэтому V = a²h / 3. "
                "Коэффициент одна треть относится к пространственной "
                "форме пирамиды, а не к тому, сколько сторон имеет её основание."
            ), r"S_{\text{осн}}=a^2,\qquad V=\frac{a^2h}{3}"),
            _section("Сначала площадь, затем объём", (
                "Возведите сторону квадрата в "
                "квадрат. Полученную площадь "
                "умножьте на высоту и "
                "разделите на три. "
                "При удобных числах "
                "можно сначала сократить "
                "высоту или площадь "
                "с делителем, сохраняя "
                "точную дробь до конца. "
                "Округлять результат деления "
                "раньше последнего действия нельзя. Периметр квадрата "
                "в этой формуле не участвует: умножение "
                "четырёх сторон на высоту не даёт объём. "
                "Единицы помогают заметить подмену: площадь "
                "основания измеряется в квадратных сантиметрах, "
                "высота — в сантиметрах, а итог — в кубических. "
                "Если исходные единицы различны, согласуйте их до возведения в квадрат."
            )),
            _section("Проверяем смысл полученного числа", (
                "Объём должен быть положительным "
                "и втрое меньше объёма "
                "призмы с теми же "
                "площадью основания и "
                "высотой. При увеличении "
                "только высоты вдвое "
                "объём удваивается; при "
                "удвоении только стороны "
                "квадратного основания — "
                "увеличивается вчетверо. "
                "Это разные изменения, поскольку сторона входит "
                "в формулу в квадрате. Для существования "
                "пирамиды достаточно положительной стороны квадрата "
                "и положительной высоты. Если бы вместо "
                "высоты дали боковое ребро, потребовались "
                "бы сведения о расположении вершины и "
                "дополнительная геометрическая задача. Нельзя восстановить "
                "высоту из ребра одной лишь заменой обозначения в знакомой формуле."
            )),
        ],
        "example": {
            "statement": (
                "В основании пирамиды квадрат со стороной 6 см. Высота пирамиды 10 см. Найдите "
                "объём в см³."
            ),
            "steps": [
                "Площадь основания равна 6² = 36 см².",
                "V = 36 · 10 / 3 = 120 см³.",
                "Для проверки призма с тем же основанием и высотой имела бы объём 360 см³.",
                "Положение вершины над плоскостью не использовалось: данная высота уже "
                "перпендикулярна основанию.",
            ],
            "answer": "120",
        },
        "takeaway": (
            "У пирамиды объём равен трети произведения площади основания на перпендикулярную "
            "высоту."
        ),
    },
    "cylinder-volume-coefficient": {
        "sections": [
            _section("Радиус и высота цилиндра", (
                "Прямой круговой цилиндр имеет "
                "два равных круглых основания "
                "в параллельных плоскостях. "
                "Радиус r относится к "
                "кругу основания, а "
                "высота h — к "
                "расстоянию между плоскостями. "
                "Если указан диаметр, "
                "его сначала делят "
                "пополам. Подстановка диаметра "
                "вместо радиуса увеличит вычисленную площадь основания "
                "вчетверо, потому что величина возводится в "
                "квадрат. В этой серии радиус назван "
                "прямо, так что дополнительных пространственных "
                "построений не требуется. Положительные радиус "
                "и высота задают невырожденное тело, а положение цилиндра на рисунке на объём не "
                "влияет."
            )),
            _section("Площадь круга умножается на высоту", (
                "Все сечения цилиндра плоскостями, "
                "параллельными основаниям, являются "
                "равными кругами. Поэтому "
                "объём вычисляется как "
                "площадь основания, умноженная "
                "на высоту. Площадь "
                "круга равна πr², "
                "следовательно V = πr²h. "
                "Длина окружности 2πr "
                "не подходит вместо "
                "площади: умножение её на высоту даёт "
                "боковую поверхность цилиндра. Это полезное "
                "сопоставление, когда две знакомые формулы "
                "путаются. Размерность тоже различается: "
                "r²h содержит три линейных множителя "
                "и измеряется в кубических единицах, "
                "а rh содержит два и описывает площадь, не объём внутреннего пространства."
            ), r"V=\pi r^2h"),
            _section("Почему не нужно приближать π", (
                "Вопрос сформулирован через запись "
                "V = kπ см³. Требуется "
                "число k, то есть "
                "коэффициент перед π "
                "при измерении объёма "
                "в кубических сантиметрах. "
                "Сопоставив запись с "
                "формулой, получаем k = r²h "
                "для числовых значений "
                "размеров в сантиметрах. "
                "Сам объём при ненулевом рациональном k "
                "содержит иррациональный множитель π, но "
                "это не мешает коэффициенту быть точным "
                "целым или конечным десятичным числом. "
                "Подстановка 3,14 здесь изменила бы "
                "предмет вопроса и создала ненужную погрешность. "
                "Записывайте отдельно выражение для объёма и отдельно число, которое "
                "действительно требуется в ответе."
            )),
            _section("Контроль степени и единиц", (
                "При удвоении высоты объём "
                "увеличивается вдвое, при "
                "удвоении радиуса — "
                "вчетверо. Эти зависимости "
                "следуют непосредственно из "
                "формулы и помогают "
                "проверить, что квадрат "
                "поставлен именно у "
                "радиуса. Если все "
                "размеры увеличить вдвое, "
                "объём возрастёт восемь раз. Число k "
                "зависит от выбранных единиц объёма, "
                "поэтому указание см³ нельзя игнорировать. "
                "Если размеры были бы в метрах, "
                "а объём требовался в см³, понадобился "
                "бы согласованный перевод. Для задач "
                "этого урока все размеры уже согласованы; "
                "последняя проверка состоит в восстановлении V = kπ и сравнении с исходной "
                "формулой."
            )),
        ],
        "example": {
            "statement": "Радиус цилиндра 5 см, высота 7 см. Объём V = kπ см³. Найдите k.",
            "steps": [
                "Площадь основания равна π · 5² = 25π см².",
                "Объём V = 25π · 7 = 175π см³.",
                "В записи V = kπ коэффициент k равен 175.",
                "Значение π не заменялось приближением; в ответ входит только число перед ним.",
            ],
            "answer": "175",
        },
        "takeaway": (
            "Для V = kπ сначала найдите r²h. Коэффициент k вычисляется точно без десятичного "
            "приближения π."
        ),
    },
    "cone-surface-coefficient": {
        "sections": [
            _section("Три длины в осевом сечении", (
                "У прямого кругового конуса "
                "вершина расположена над центром "
                "основания. Высота соединяет "
                "вершину с центром "
                "и перпендикулярна основанию. "
                "Образующая соединяет вершину "
                "с точкой окружности "
                "основания и идёт "
                "по боковой поверхности. "
                "Радиус, высота и "
                "образующая составляют прямоугольный треугольник, в "
                "котором образующая — гипотенуза. Полное "
                "осевое сечение имеет в основании "
                "диаметр, но при применении Пифагора "
                "берётся половина этого сечения, поэтому "
                "один катет равен радиусу. Именно здесь часто возникает ошибочная подстановка "
                "диаметра вместо радиуса."
            )),
            _section("Боковая и полная поверхности", (
                "Площадь боковой поверхности конуса "
                "равна πrl, где l — "
                "образующая. Её можно "
                "понять через развёртку "
                "в круговой сектор: "
                "радиус сектора равен "
                "l, а длина его "
                "дуги совпадает с "
                "длиной окружности основания. "
                "Полная поверхность включает "
                "также круг основания площадью πr². "
                "Следовательно S = πrl + πr². "
                "Если дана высота, сначала найдите "
                "l = √(r² + h²). Заменять "
                "образующую высотой нельзя: при положительном "
                "радиусе образующая строго длиннее. Слово "
                "«полная» определяет необходимость второго слагаемого, даже если рисунок "
                "показывает только боковую часть."
            ), r"l=\sqrt{r^2+h^2},\quad S_{\text{полн}}=\pi r(l+r)"),
            _section("Точное извлечение коэффициента", (
                "В задачах этого урока "
                "полная площадь записывается "
                "как S = kπ см². "
                "После нахождения образующей "
                "вычислите k = rl + r² "
                "или равносильное выражение "
                "r(l + r). При "
                "целых r и l "
                "этот коэффициент целый, "
                "хотя сама площадь "
                "содержит π. Радиус и высота в "
                "серии подобраны из точных прямоугольных "
                "треугольников, поэтому корень не требует "
                "округления. Полезно держать два слагаемых "
                "раздельно до конца: одно отвечает "
                "за боковую часть, второе — за "
                "основание. Тогда проще заметить пропущенный круг и проверить размерности "
                "каждого промежуточного выражения."
            )),
            _section("Оценка и ограничения", (
                "Полная площадь должна превышать "
                "площадь основания. Кроме "
                "того, поскольку l больше "
                "r, боковая поверхность "
                "также больше площади "
                "основания для положительной "
                "высоты. Значит k больше "
                "2r². Это быстрый "
                "контроль величины ответа. "
                "При увеличении всех "
                "длин в одинаковое число раз "
                "площадь возрастает в квадрат этого "
                "числа. Формула с единой образующей "
                "относится к прямому круговому конусу; "
                "для наклонного конуса образующие могут "
                "иметь разные длины. Поэтому условие "
                "прямого конуса нельзя молча отбросить. "
                "Ответом служит коэффициент при π в квадратных единицах, а не объём и не сама "
                "образующая."
            )),
        ],
        "example": {
            "statement": (
                "Радиус прямого конуса 5 см, высота 12 см. Полная поверхность S = kπ см². "
                "Найдите k."
            ),
            "steps": [
                "Образующая l = √(5² + 12²) = √169 = 13 см.",
                "Боковая поверхность равна 5 · 13π = 65π см²; основание — 25π см².",
                "Полная поверхность равна 90π см², поэтому k = 90.",
                "Проверка: образующая длиннее радиуса и высоты, а коэффициент 90 больше 2 · 25.",
            ],
            "answer": "90",
        },
        "takeaway": (
            "По высоте и радиусу найдите образующую; к боковой поверхности обязательно добавьте "
            "основание."
        ),
    },
    "sphere-volume-coefficient": {
        "sections": [
            _section("Шар и сфера описывают разные объекты", (
                "Шар — пространственное тело, "
                "состоящее из всех точек "
                "на расстоянии не больше "
                "радиуса от центра. "
                "Сфера — его граница, "
                "то есть поверхность "
                "точек на расстоянии "
                "ровно радиуса. Объём "
                "относится к шару, "
                "площадь — к сфере. "
                "Обе формулы содержат π и число "
                "четыре, поэтому их легко перепутать, "
                "если не прочитать вопрос. Радиус "
                "соединяет центр с поверхностью, диаметр "
                "проходит через центр и вдвое "
                "больше радиуса. В этом семействе "
                "радиус указан непосредственно, так что первым действием делить его пополам не "
                "требуется."
            )),
            _section("Куб радиуса в формуле объёма", (
                "Объём шара радиуса r равен "
                "четырём третям произведения π "
                "на куб радиуса. Куб "
                "означает произведение трёх "
                "одинаковых линейных множителей, "
                "поэтому размерность получается "
                "кубической. В формуле "
                "площади сферы радиус "
                "возводится в квадрат, "
                "а множителя одна "
                "треть нет. Сравнение размерностей помогает "
                "восстановить правильный выбор, но сам "
                "числовой коэффициент четыре третьих нужно "
                "знать как теорему об объёме шара. "
                "Вычисление не требует разрезать тело "
                "или находить площади отдельных кругов: "
                "один радиус полностью задаёт размер шара и тем самым его объём."
            ), r"V=\frac43\pi r^3"),
            _section("Коэффициент вместо приближённого объёма", (
                "Если условие записывает объём "
                "в форме V = kπ см³, "
                "искомое число равно "
                "k = 4r³ / 3 при "
                "радиусе в сантиметрах. "
                "Ни число π, ни "
                "сам объём округлять "
                "не надо. При "
                "радиусе, кратном трём, "
                "деление сокращается сразу. "
                "При дробном радиусе удобно перевести "
                "его в точную обыкновенную дробь, "
                "возвести числитель и знаменатель в "
                "куб, затем сократить множители. Промежуточная "
                "дробь не должна заменяться близким "
                "десятичным числом. В разобранном примере "
                "получится конечная десятичная запись коэффициента, хотя выражение полного "
                "объёма сохранит множитель π."
            )),
            _section("Проверка масштаба", (
                "При удвоении радиуса объём "
                "возрастает в восемь раз, "
                "а не в два "
                "и не в четыре. "
                "Это отражает изменение "
                "всех трёх пространственных "
                "измерений. Объём положителен "
                "при положительном радиусе "
                "и стремится к нулю "
                "при уменьшении радиуса. "
                "Эти качественные проверки помогают заметить "
                "перепутанную степень или обратную дробь. "
                "Следите также за единицами: коэффициент "
                "перед π в кубических сантиметрах "
                "не совпадает с коэффициентом в "
                "кубических метрах. Нельзя перевести его "
                "простым линейным множителем сто. Сначала "
                "согласуйте единицу радиуса с требуемой единицей объёма, а затем применяйте "
                "кубическую зависимость."
            )),
        ],
        "example": {
            "statement": "Радиус шара равен 4,5 см. Его объём V = kπ см³. Найдите k.",
            "steps": [
                "Записываем радиус точно: r = 9/2 см, поэтому r³ = 729/8 см³.",
                "Коэффициент k = (4/3) · (729/8) = 243/2 = 121,5.",
                "Таким образом, V = 121,5π см³, а ответ на вопрос о коэффициенте — 121,5.",
                "Промежуточные дроби сокращались точно; подстановка приближённого π не "
                "использовалась.",
            ],
            "answer": "121,5",
        },
        "takeaway": (
            "Различайте объём шара и площадь сферы: для объёма коэффициент при π равен 4r³/3."
        ),
    },
    "solid-similarity-volume": {
        "sections": [
            _section("Подобие относится ко всем размерам", (
                "Подобные тела имеют одинаковую "
                "форму, а все соответствующие "
                "линейные размеры относятся "
                "как одно положительное "
                "число k. Знать "
                "отношение одной пары "
                "рёбер достаточно только "
                "потому, что подобие "
                "явно дано. У двух "
                "произвольных призм одинаковое "
                "отношение отдельных рёбер не определяет отношение "
                "объёмов: остальные размеры могли измениться "
                "иначе. Начните с выбора направления "
                "сравнения. Если ищется объём большей "
                "призмы по меньшей, удобно взять "
                "k как ребро большей, делённое "
                "на соответствующее ребро меньшей. Тогда коэффициент будет больше единицы, что "
                "сразу задаёт ожидаемый рост."
            )),
            _section("Почему объём меняется в куб", (
                "Для призмы объём равен площади "
                "основания, умноженной на высоту. "
                "При подобии все длины "
                "основания увеличиваются в k "
                "раз, поэтому его площадь "
                "увеличивается в k² раз. "
                "Высота как линейный размер "
                "увеличивается ещё в k "
                "раз. Произведение даёт "
                "k³. Так возникает "
                "закон отношения объёмов подобных тел. "
                "Он не является специальным свойством "
                "только прямых призм: тот же "
                "пространственный масштаб действует для любых "
                "подобных тел. В данном уроке "
                "призмы позволяют проследить причину "
                "показателя степени через знакомую формулу, а не просто запомнить куб как "
                "отдельный приём."
            ), r"V_{\text{б}}=V_{\text{м}}\left(\frac{a_{\text{б}}}{a_{\text{м}}}\right)^3"),
            _section("Точное отношение удобнее десятичного", (
                "Составьте дробь из соответствующих "
                "рёбер и сократите её, "
                "если возможно. Возведите "
                "в куб и числитель, "
                "и знаменатель. Затем "
                "умножьте известный объём "
                "на полученное отношение. "
                "Сокращение с известным "
                "объёмом нередко полностью "
                "убирает знаменатель. Даже "
                "если линейное отношение имеет бесконечную "
                "десятичную запись, итог может оказаться "
                "целым. Поэтому раннее округление "
                "не оправдано. Если вопрос направлен "
                "обратно, от большей призмы к "
                "меньшей, используйте обратное отношение "
                "или деление на k³. Подписи «большая» и «меньшая» возле дроби помогают избежать "
                "перевёрнутого коэффициента."
            )),
            _section("Различаем три степени масштаба", (
                "Линейные размеры и периметры "
                "меняются в k раз, "
                "площади — в k², "
                "объёмы — в k³. "
                "При удвоении всех "
                "размеров это соответственно "
                "два, четыре и "
                "восемь раз. В "
                "задаче на объём "
                "ответ, полученный умножением "
                "только на линейный коэффициент, будет "
                "слишком мал для увеличения тела. "
                "Проверьте положительность размеров и "
                "согласованность единиц соответствующих рёбер. "
                "Сам коэффициент подобия безразмерен, "
                "поэтому единица объёма сохраняется "
                "при умножении. Если одна призма "
                "просто выше другой при том же основании, они обычно не подобны, и применять куб "
                "высот нельзя."
            )),
        ],
        "example": {
            "statement": (
                "Подобные призмы имеют соответствующие рёбра 4 см и 10 см. Объём меньшей 32 см³. "
                "Найдите объём большей."
            ),
            "steps": [
                "Коэффициент увеличения k = 10/4 = 5/2.",
                "Объёмы относятся как k³ = 125/8.",
                "Объём большей призмы равен 32 · 125/8 = 500 см³.",
                "Отношение 500/32 равно 125/8; увеличение относится ко всем линейным размерам, а "
                "не только к ребру.",
            ],
            "answer": "500",
        },
        "takeaway": (
            "При доказанном или данном подобии умножайте объём на куб отношения соответствующих "
            "длин."
        ),
    },
})

_LESSONS.update({
    "urn-favorable-count": {
        "sections": [
            _section("Исход — отдельный шар, а не цвет", (
                "Классическая формула вероятности работает, "
                "когда все элементарные исходы "
                "равновозможны. В задаче с "
                "мешком такими исходами служат "
                "отдельные шары. Их можно "
                "мысленно пронумеровать, даже "
                "если в реальности номера "
                "не нанесены. Два названия "
                "цветов не становятся двумя "
                "равновозможными исходами автоматически: "
                "одного цвета может быть гораздо больше. Условие "
                "об одинаковой вероятности выбора каждого шара "
                "обосновывает подсчёт. Фраза «наугад» без "
                "уточнения модели иногда бывает недостаточной, "
                "но здесь равновозможность задана прямо. "
                "Именно она позволяет заменить анализ механики перемешивания простой долей "
                "нужных шаров."
            )),
            _section("Событие объединяет подходящие исходы", (
                "Событие «вынут красный шар» "
                "включает все элементарные исходы, "
                "связанные с красными шарами. "
                "Если их r, а "
                "всего шаров N, "
                "каждый отдельный исход "
                "имеет вероятность 1/N. "
                "Сложение r одинаковых "
                "вероятностей даёт r/N. "
                "Это и есть отношение "
                "числа благоприятных исходов к числу всех "
                "равновозможных исходов. Знаменатель включает оба "
                "цвета. Делить красные только на "
                "синие нельзя: такое отношение сравнивает "
                "численности групп, но не задаёт "
                "вероятность выбора из всего мешка. "
                "Требуемое число описывает один выбор, а не серию извлечений с меняющимся составом."
            ), r"P(\text{красный})=\frac{r}{r+b}"),
            _section("От условия к точной дроби", (
                "Сначала сложите количества красных "
                "и синих шаров. Затем "
                "поставьте количество красных "
                "в числитель и общий "
                "итог в знаменатель. "
                "Сократите дробь до "
                "перевода в десятичную "
                "запись. Если ответ "
                "требуется вероятностью, не "
                "умножайте его дополнительно "
                "на сто: это перевело бы число "
                "в проценты. Например, доля 0,28 "
                "и двадцать восемь процентов описывают "
                "одно отношение, но в поле "
                "числовой вероятности вводится 0,28. "
                "Конечность десятичной записи в этой "
                "серии обеспечена подбором общего количества шаров; «примерно» и скрытое "
                "округление не входят в условие."
            )),
            _section("Проверки модели и ответа", (
                "Вероятность неотрицательна и не "
                "превосходит единицу. Если "
                "есть шары обоих цветов, "
                "она строго между "
                "этими границами. Когда "
                "красных меньше синих, "
                "вероятность красного меньше "
                "половины; при одинаковых "
                "количествах равна половине. "
                "Дополнительно посчитайте долю "
                "синих: две доли должны дать единицу. "
                "Если шар одного цвета тяжелее "
                "или механизм специально предпочитает "
                "некоторые шары, классический подсчёт "
                "не обязательно остаётся верным. "
                "Этот урок учит выбирать пространство "
                "равновозможных исходов, а не угадывать "
                "вероятность по числу названных категорий. При изменении модели выбора сначала "
                "пересмотрите исходы."
            )),
        ],
        "example": {
            "statement": (
                "В мешке 7 красных и 18 синих равновероятно выбираемых шаров. Найдите "
                "вероятность красного."
            ),
            "steps": [
                "Всего 7 + 18 = 25 элементарных исходов — отдельных шаров.",
                "Благоприятных исходов 7, поэтому P = 7/25 = 28/100 = 0,28.",
                "Доля синих равна 18/25 = 0,72; сумма двух вероятностей равна единице.",
                "Вероятность красного меньше половины, поскольку красных шаров меньше синих.",
            ],
            "answer": "0,28",
        },
        "takeaway": (
            "Считайте равновозможные предметы. Вероятность — нужное количество, делённое на "
            "общее."
        ),
    },
    "integer-event-boundaries": {
        "sections": [
            _section("Слова задают включение концов", (
                "В задачах с целыми номерами "
                "главная трудность часто "
                "не в дробях, а "
                "в границах события. "
                "Слова «больше l» "
                "означают строгое неравенство: "
                "сам номер l "
                "не подходит. Слова "
                "«не превосходит u» "
                "означают, что номер "
                "u включается. Вместе получаем l < X ≤ u. "
                "Сначала переведите условие в такую "
                "запись, а уже потом считайте "
                "карточки. Замена одного слова "
                "может изменить число подходящих "
                "исходов на единицу, и для "
                "конечного набора это меняет вероятность, даже если два интервала выглядят почти "
                "одинаково. "
                "Короткий промежуток можно проверить перечислением; это полезно, если одна "
                "из границ совпадает с концом всего набора карточек."
            )),
            _section("Сколько целых чисел между границами", (
                "Для включённого промежутка от "
                "первого целого числа a "
                "до последнего b "
                "количество чисел равно "
                "b − a + 1. "
                "Единица учитывает оба "
                "конца. В нашем "
                "событии первым подходящим "
                "номером будет l + 1, "
                "а последним — u. "
                "Подстановка даёт u − (l + 1) + 1 = u − l. "
                "Это не универсальное правило для "
                "любого интервала: если включить "
                "обе границы, получится на "
                "один исход больше; если "
                "обе исключить — на один "
                "меньше. Полезно сначала явно назвать первый и последний номера, чтобы формула "
                "следовала из смысла."
            ), r"\#\{X\in\mathbb Z:l<X\le u\}=u-l"),
            _section("Нормировка на все карточки", (
                "Карточки пронумерованы от единицы "
                "до N включительно, значит "
                "всего имеется N "
                "равновозможных исходов. "
                "Делите число подходящих "
                "номеров на N, "
                "а не на верхнюю "
                "границу события. Верхняя "
                "граница может находиться "
                "в середине всей "
                "нумерации и не описывает размер выборки. "
                "В задачах урока обе границы "
                "уже находятся внутри допустимых "
                "номеров. В более общем случае "
                "сначала пересеките событие с "
                "реальным диапазоном карточек: номера "
                "за его пределами нельзя считать исходами. "
                "Работайте с точной дробью, чтобы небольшая разница в одном номере не потерялась "
                "при округлении."
            )),
            _section("Проверка через соседние события", (
                "Проверьте отдельно карточки с "
                "номерами l и u: "
                "первая должна быть "
                "исключена, вторая включена. "
                "Затем посмотрите на "
                "соседние l + 1 "
                "и u + 1, "
                "если они существуют "
                "в наборе. Этот "
                "локальный контроль надёжнее "
                "повторного чтения одной и той же "
                "формулы. Если повысить верхнюю "
                "границу на единицу внутри "
                "набора, вероятность возрастёт ровно "
                "на 1/N. Если повысить нижнюю, "
                "она уменьшится на 1/N. "
                "Такая проверка показывает направление изменения. "
                "Для непрерывной случайной величины отдельная точка может иметь нулевую "
                "вероятность, но у карточки здесь она положительна."
            )),
        ],
        "example": {
            "statement": (
                "Из карточек с номерами 1–80 выбирают одну равновероятно. Найдите вероятность 17 "
                "< X ≤ 43."
            ),
            "steps": [
                "Подходят номера 18, 19, …, 43. Номер 17 исключён, 43 включён.",
                "Количество равно 43 − 18 + 1 = 26.",
                "P = 26/80 = 13/40 = 0,325.",
                "Знаменатель 80 описывает весь набор, а не только событие до номера 43.",
            ],
            "answer": "0,325",
        },
        "takeaway": "Выпишите первый и последний подходящие номера; для l < X ≤ u их ровно u − l.",
    },
    "complement-quality": {
        "sections": [
            _section("Когда события действительно противоположны", (
                "Противоположное событие к A "
                "происходит ровно тогда, "
                "когда A не "
                "происходит. Два таких "
                "события не могут "
                "произойти одновременно и "
                "вместе охватывают все "
                "возможные исходы. В "
                "задаче изделие либо "
                "годное, либо бракованное, "
                "а третьего состояния нет. Поэтому годность "
                "и брак противоположны. Обычная несовместность "
                "ещё недостаточна: например, красный "
                "и синий цвета не были "
                "бы противоположными событиями при "
                "наличии зелёных изделий. Сначала проверьте "
                "полноту двух вариантов, чтобы вычитание из единицы было логически обоснованным, "
                "а не просто привычным действием."
            )),
            _section("Почему сумма равна единице", (
                "Вероятность достоверного события равна "
                "единице. Поскольку A "
                "и его дополнение "
                "делят весь набор "
                "исходов на две "
                "непересекающиеся части, их "
                "вероятности в сумме "
                "дают единицу. Отсюда "
                "вероятность противоположного события "
                "равна 1 − P(A). "
                "Для этого правила не требуется, "
                "чтобы элементарные исходы были "
                "равновозможны. В условии может "
                "быть просто дана вероятность "
                "брака, полученная из некоторой "
                "модели. Правило дополнения остаётся "
                "верным без восстановления количества изделий "
                "или объёма партии. Это отличает данный способ от прямого подсчёта благоприятных "
                "предметов в мешке."
            ), r"P(\overline A)=1-P(A)"),
            _section("Точная десятичная арифметика", (
                "Если вероятность дана конечной "
                "десятичной дробью, вычтите "
                "её из единицы "
                "с сохранением всех "
                "разрядов. Для трёх "
                "знаков после запятой "
                "удобно мысленно записать "
                "единицу как одну "
                "тысячу тысячных. Тогда "
                "из тысячи вычитается "
                "числитель исходной вероятности. При таком "
                "подходе не теряются нули "
                "в начале дробной части. "
                "Не делите единицу на "
                "вероятность: обратное число вообще "
                "может оказаться больше единицы "
                "и не имеет требуемого смысла. "
                "Не переводите ответ в проценты, если вопрос требует вероятность. В записи 0,963 "
                "именно запятая отделяет дробную часть."
            )),
            _section("Смысловая проверка", (
                "Сложите найденную вероятность годности "
                "с данной вероятностью "
                "брака: результат должен "
                "точно равняться единице. "
                "Если брак редок, "
                "вероятность годного изделия "
                "близка к единице. "
                "Если брак встречается "
                "чаще половины случаев, "
                "вероятность годности меньше "
                "половины. Граничные случаи тоже понятны: "
                "при нулевой вероятности брака "
                "годность достоверна, при вероятности "
                "брака один невозможна. Однако "
                "результат одного случайного выбора "
                "не предопределён промежуточной вероятностью: "
                "число описывает модель, а не "
                "гарантирует качество конкретного следующего изделия. Этот урок учит работе с "
                "противоположным событием, а не статистической оценке надёжности производства."
            )),
        ],
        "example": {
            "statement": (
                "Изделие либо годное, либо бракованное. Вероятность брака 0,037. Найдите "
                "вероятность годности."
            ),
            "steps": [
                "События противоположны: несовместны и вместе исчерпывают все исходы.",
                "Вероятность годности равна 1 − 0,037 = 0,963.",
                "Точный счёт в тысячных: (1000 − 37)/1000 = 963/1000.",
                "Проверка: 0,963 + 0,037 = 1; редкому браку соответствует высокая вероятность "
                "годности.",
            ],
            "answer": "0,963",
        },
        "takeaway": (
            "Убедитесь, что два события исчерпывают исходы, и вычтите известную вероятность из "
            "единицы."
        ),
    },
    "coin-pattern-enumeration": {
        "sections": [
            _section("Исходом является вся последовательность", (
                "При нескольких бросках монеты "
                "элементарный исход описывает "
                "результаты всех бросков "
                "в их порядке. "
                "Последовательности ОРР и "
                "РОР различны, хотя "
                "обе содержат одного "
                "орла. Симметричность монеты "
                "означает одинаковые вероятности "
                "орла и решки "
                "в каждом броске; независимость означает, "
                "что предыдущие результаты не меняют "
                "вероятности следующего. Вместе эти "
                "условия делают все последовательности "
                "одной длины равновозможными. Само "
                "число орлов, наоборот, не "
                "принимает все значения равновероятно: "
                "некоторым количествам соответствует больше последовательностей. Поэтому считать "
                "исходами просто числа от нуля до количества бросков нельзя."
            )),
            _section("Систематический перебор вместо угадывания", (
                "На каждом месте последовательности "
                "имеются два варианта. "
                "Для n бросков "
                "получается 2 в "
                "степени n полных "
                "последовательностей. Чтобы "
                "выписать их без "
                "пропусков, можно сначала "
                "разбить на начинающиеся "
                "с орла и "
                "с решки, затем каждую группу "
                "снова разделить по второму "
                "броску. Такой двоичный перебор "
                "даёт каждую последовательность ровно "
                "один раз. Для коротких "
                "серий из трёх–шести бросков "
                "удобно также выбирать места "
                "орлов, а на оставшиеся места ставить решки. Считать перестановки одинаковых "
                "орлов между собой не нужно: последовательность от этого не меняется."
            ), r"N=2^n,\qquad P(A)=\frac{m}{2^n}"),
            _section("Слово «ровно» ограничивает событие", (
                "Условие «ровно k орлов» "
                "включает только последовательности "
                "с указанным количеством. "
                "Меньшее и большее "
                "количества исключаются. "
                "Это отличается от "
                "«не менее k» "
                "или «хотя бы "
                "k», где нужны "
                "и все большие "
                "значения. После отбора благоприятных последовательностей "
                "разделите их количество на "
                "общее. Для трёх бросков "
                "можно выписать все варианты "
                "восемью строками и поставить "
                "отметки возле подходящих. Для "
                "более длинной серии удобнее "
                "упорядочить выбор мест, но смысл остаётся тем же. В этом уроке проверяется "
                "конечное пространство исходов, а не приближённая частота в эксперименте."
            )),
            _section("Как убедиться, что перебор полный", (
                "Каждый благоприятный вариант должен "
                "иметь нужную длину "
                "и ровно нужное "
                "число орлов. Проверьте, "
                "что один вариант "
                "не записан дважды "
                "под разными описаниями. "
                "Замена всех орлов "
                "решками показывает симметрию: "
                "вероятности k орлов "
                "и n − k орлов равны. "
                "Если подсчитать благоприятные количества "
                "для всех возможных k, "
                "их сумма должна дать "
                "2 в степени n. "
                "Это проверяет нормировку распределения "
                "и выявляет пропущенные варианты. "
                "Отдельная последовательность может быть редкой, но группа последовательностей с "
                "одним количеством орлов имеет суммарную вероятность и не должна подменяться "
                "вероятностью одного варианта."
            )),
        ],
        "example": {
            "statement": (
                "Симметричную монету независимо бросают три раза. Найдите вероятность ровно двух "
                "орлов."
            ),
            "steps": [
                "Полный список: ООО, ООР, ОРО, ОРР, РОО, РОР, РРО, РРР. Всего восемь исходов.",
                "Ровно два орла имеют ООР, ОРО и РОО: три благоприятных исхода.",
                "P = 3/8 = 0,375. Вариант ООО не включается, потому что в нём три орла.",
                "Симметрично ровно одна решка имеет ту же вероятность, поскольку это то же самое "
                "событие.",
            ],
            "answer": "0,375",
        },
        "takeaway": (
            "Перебирайте упорядоченные последовательности и отбирайте ровно указанное количество "
            "орлов."
        ),
    },
    "spinner-sector": {
        "sections": [
            _section("Равномерность относится к направлениям", (
                "Круговой указатель после вращения "
                "может остановиться в "
                "любом направлении. Равномерность "
                "означает, что равные "
                "угловые промежутки имеют "
                "равные вероятности, где "
                "бы на круге "
                "они ни находились. "
                "Два цвета не "
                "обязаны иметь одинаковые "
                "шансы: красная часть может занимать "
                "меньший угол, чем синяя. "
                "В отличие от задачи с "
                "конечным набором шаров здесь "
                "нельзя сосчитать отдельные направления "
                "по одному. Вместо количества "
                "исходов сравниваются угловые размеры. "
                "Равномерность — существенное условие модели, а не автоматическое свойство "
                "любого физического устройства со стрелкой."
            )),
            _section("Доля полного оборота", (
                "Полный круг соответствует трёмстам "
                "шестидесяти градусам и "
                "вероятности один. Сектор "
                "с центральным углом "
                "α занимает долю "
                "α/360 полного оборота. "
                "При равномерном направлении "
                "такая же доля "
                "приходится на вероятность "
                "попасть в сектор. "
                "Радиус указателя и длина стрелки "
                "для этого отношения не "
                "нужны. Если выразить размер "
                "сектора длиной дуги, получится "
                "отношение дуги к полной "
                "длине окружности, в котором "
                "радиус сократится. Сравнение площадей "
                "секторов того же круга тоже даст ту же долю, но угловая запись напрямую "
                "соответствует случайному направлению стрелки."
            ), r"P(\text{сектор})=\frac{\alpha}{360^\circ}"),
            _section("Что происходит на границах", (
                "В равномерной непрерывной модели "
                "вероятность остановиться точно "
                "на одном заданном "
                "луче равна нулю. "
                "Поэтому включение или "
                "исключение двух граничных "
                "лучей не меняет "
                "вероятность сектора. В "
                "условии это свойство "
                "указано явно, чтобы "
                "не возникало вопроса о цвете "
                "линии между секторами. Это "
                "отличается от выбора целочисленной "
                "карточки: там крайний номер "
                "имеет положительную вероятность и "
                "влияет на ответ. Не "
                "переносите автоматически правило границ "
                "из дискретной модели в непрерывную. Если устройство фиксирует лишь конечный "
                "набор направлений, потребуется отдельное описание этих положений и их "
                "вероятностей."
            )),
            _section("Вычисление без лишней геометрии", (
                "Разделите угол красного сектора "
                "на полный угол "
                "оборота и сократите "
                "дробь. Число π "
                "не появляется, потому "
                "что обе величины "
                "уже выражены в "
                "градусах. Оцените ответ: "
                "сектор меньше половины "
                "круга должен иметь "
                "вероятность меньше половины. Сумма вероятностей "
                "красной и оставшейся синей "
                "частей равна единице. Если "
                "два непересекающихся красных сектора "
                "были бы даны отдельно, "
                "сначала можно было бы "
                "сложить их углы. В "
                "этой серии сектор один, а его угол подобран так, чтобы дробь переводилась в "
                "точную конечную десятичную запись без скрытого округления."
            )),
        ],
        "example": {
            "statement": (
                "Направление стрелки равномерно. Красный сектор имеет угол 126°. Граничные лучи "
                "имеют нулевую вероятность. Найдите вероятность красного."
            ),
            "steps": [
                "Красный сектор занимает 126/360 полного оборота.",
                "Сокращаем дробь: 126/360 = 7/20 = 0,35.",
                "Вероятность синего равна 234/360 = 0,65; сумма равна единице.",
                "Угол 126° меньше половины полного оборота, поэтому результат меньше 0,5, как и "
                "ожидалось.",
            ],
            "answer": "0,35",
        },
        "takeaway": (
            "При равномерном направлении вероятность сектора равна его угловой доле полного "
            "оборота."
        ),
    },
})

_LESSONS.update({
    "independent-at-least-one": {
        "sections": [
            _section("«Хотя бы один» включает совместный успех", (
                "Событие «хотя бы один "
                "датчик обнаружил сигнал» "
                "означает успех первого, "
                "успех второго или "
                "успех обоих сразу. "
                "В отличие от "
                "«ровно одного», совместное "
                "срабатывание не исключается. "
                "Можно перечислить три "
                "подходящих сочетания, но "
                "короче рассмотреть единственное неподходящее: "
                "ни один датчик не обнаружил "
                "сигнал. Оно противоположно искомому "
                "событию. Выбор дополнения сокращает "
                "число путей, по которым "
                "нужно считать вероятность. Этот "
                "приём особенно удобен при большем числе "
                "датчиков, однако прежде чем перемножать вероятности, требуется обосновать "
                "независимость соответствующих испытаний. "
                "При одинаковых датчиках речь всё равно идёт о двух событиях: одинаковые "
                "численные вероятности не означают один и тот же случайный исход."
            )),
            _section("Независимость разрешает умножение", (
                "Независимость означает, что результат "
                "одного датчика не меняет "
                "вероятность результата другого. "
                "Это задано в "
                "условии, а не "
                "выводится просто из "
                "того, что датчиков "
                "два. Если вероятности "
                "обнаружения равны p "
                "и q, вероятности "
                "необнаружения равны 1 − p и "
                "1 − q. Противоположные события "
                "тоже независимы, поэтому вероятность "
                "двух необнаружений равна произведению "
                "этих чисел. После этого "
                "остаётся вычесть результат из "
                "единицы. Если оба датчика зависят "
                "от одной неизвестной причины отказа, пользоваться этим произведением без "
                "дополнительной модели было бы неверно."
            ), r"P(\text{хотя бы один})=1-(1-p)(1-q)"),
            _section("Почему простая сумма завышает результат", (
                "Сложение p + q учитывает "
                "случай совместного обнаружения "
                "дважды. Для независимых "
                "датчиков его вероятность "
                "равна pq, поэтому "
                "нужно вычесть одно "
                "такое пересечение. Получается "
                "другая форма той "
                "же зависимости: p + q − pq. "
                "Раскройте скобки в "
                "формуле дополнения, чтобы увидеть равенство "
                "двух способов. Это полезная "
                "проверка, а не дополнительное "
                "условие. Простая сумма допустима "
                "для несовместных событий, но "
                "независимость и несовместность — "
                "разные понятия. Два независимых события "
                "с положительными вероятностями могут происходить вместе; именно этот совместный "
                "исход надо правильно учесть."
            )),
            _section("Контроль диапазона и смысла", (
                "Искомая вероятность не меньше "
                "вероятности обнаружения любым "
                "отдельным датчиком, потому "
                "что добавление второго "
                "способа обнаружения не "
                "удаляет успехи первого. "
                "При этом она "
                "не больше единицы. "
                "Если один датчик "
                "обнаруживает сигнал достоверно, "
                "ответ равен единице независимо от "
                "другого. Если один никогда "
                "не обнаруживает, ответ равен "
                "вероятности второго. Такие крайние "
                "случаи проверяют формулу без "
                "подстановки обычных чисел. Все "
                "десятичные вероятности храните точно "
                "до конца вычисления: округление промежуточного произведения может изменить "
                "короткий ответ, хотя условие никакой погрешности не разрешало."
            )),
        ],
        "example": {
            "statement": (
                "Датчики независимо обнаруживают сигнал с вероятностями 0,65 и 0,8. Найдите "
                "вероятность хотя бы одного обнаружения."
            ),
            "steps": [
                "Вероятности необнаружения равны 0,35 и 0,2.",
                "Вероятность двух необнаружений равна 0,35 · 0,2 = 0,07.",
                "Ответ: 1 − 0,07 = 0,93.",
                "Проверка через объединение: 0,65 + 0,8 − 0,65 · 0,8 = 0,93; результат не меньше "
                "0,8.",
            ],
            "answer": "0,93",
        },
        "takeaway": (
            "Для независимых испытаний «хотя бы один» удобно считать как единицу минус "
            "произведение вероятностей неудач."
        ),
    },
    "conditional-without-replacement": {
        "sections": [
            _section("Известный результат сужает пространство исходов", (
                "Условная вероятность описывает событие "
                "после того, как уже "
                "известно другое событие. "
                "В задаче сообщается, "
                "что первый вынутый "
                "шар красный. Это "
                "не предположение о "
                "будущем, которое ещё "
                "нужно включить в "
                "вероятность, а информация, "
                "по которой перестраивается модель второго выбора. "
                "Нас интересуют только возможные продолжения "
                "после первого красного шара. "
                "Вероятность самого условия должна "
                "быть положительной; иначе обычная "
                "формула условной вероятности не "
                "определена. В заданиях есть красные "
                "шары, поэтому сообщение о первом красном совместимо с исходным составом коробки."
            )),
            _section("Отсутствие возвращения меняет два количества", (
                "Если из N шаров r "
                "красных и первый "
                "красный не возвращают, "
                "в коробке остаётся "
                "N − 1 шаров. "
                "Красных среди них "
                "r − 1, синих "
                "столько же, сколько "
                "было. При равновероятном "
                "втором выборе вероятность "
                "красного равна (r − 1)/(N − 1). "
                "Уменьшить нужно и числитель, "
                "и знаменатель. Если бы "
                "первым был синий шар, "
                "числитель остался бы r. "
                "Если бы шар возвращали "
                "и вновь перемешивали, состав "
                "коробки восстановился бы и получилась другая модель. Поэтому фраза «без "
                "возвращения» существенно влияет на вычисление."
            ), r"P(R_2\mid R_1)=\frac{r-1}{N-1}"),
            _section("Условная и совместная вероятности", (
                "Вероятность того, что оба "
                "шара красные, равна "
                "вероятности первого красного, "
                "умноженной на вероятность "
                "второго красного при "
                "этом условии. Это "
                "совместное событие и "
                "другой вопрос. В "
                "данном задании первый "
                "результат уже известен, "
                "поэтому дополнительный множитель r/N не "
                "нужен. Формальное определение подтверждает "
                "это: условная вероятность равна "
                "отношению вероятности пересечения к "
                "вероятности условия. Общий множитель "
                "r/N в таком отношении "
                "сократится. Понимание этой связи "
                "защищает от привычки перемножать все встретившиеся дроби, не различая, какая "
                "информация дана и какое событие спрашивается."
            )),
            _section("Проверка зависимости", (
                "Если в исходной коробке "
                "есть оба цвета, "
                "удаление красного уменьшает "
                "долю красных. Поэтому "
                "условная вероятность второго "
                "красного должна быть "
                "меньше исходной r/N. "
                "Это показывает зависимость "
                "выборов: первый результат "
                "влияет на вероятность "
                "второго. Удаление синего, наоборот, увеличило "
                "бы долю красных. Сумма "
                "условных вероятностей красного и "
                "синего второго шара равна "
                "единице, потому что после "
                "первого выбора других цветов "
                "нет. Для аккуратного ответа "
                "проверьте положительность оставшегося количества и не забывайте: "
                "равновозможность шаров на каждом шаге не означает независимость двух шагов."
            )),
        ],
        "example": {
            "statement": (
                "В коробке 26 шаров, из них 11 красных. Без возвращения вынули красный шар. "
                "Каждый следующий шар выбирается равновероятно. "
                "Найдите вероятность красного при втором выборе."
            ),
            "steps": [
                "После известного красного шара осталось 25 шаров, среди них 10 красных.",
                "Условная вероятность второго красного равна 10/25 = 0,4.",
                "Вероятность первого красного 11/26 не умножаем: этот результат уже сообщён.",
                "Синих осталось 15; доли 10/25 и 15/25 дают единицу. Новая доля красных меньше "
                "исходной.",
            ],
            "answer": "0,4",
        },
        "takeaway": (
            "После известного красного без возвращения уменьшите на один общее число шаров и "
            "число красных."
        ),
    },
    "overlapping-event-union": {
        "sections": [
            _section("Союз «или» включает пересечение", (
                "Событие «занимается шахматами или "
                "программированием» обычно включает "
                "и тех, кто "
                "занимается обоими предметами. "
                "В условиях этой "
                "серии включение пересечения "
                "сказано явно. Если "
                "бы спрашивалось «ровно "
                "одним из двух», "
                "пересечение пришлось бы "
                "исключить, и ответ был бы другим. "
                "Начните с обозначения двух "
                "групп A и B. "
                "Их объединение состоит из "
                "трёх непересекающихся частей: только "
                "A, только B и "
                "оба занятия. Такой разбор "
                "позволяет не полагаться на бытовое понимание слова «или» и точно перевести "
                "вопрос на язык множеств."
            )),
            _section("Исправление двойного счёта", (
                "При сложении численностей A "
                "и B люди из "
                "пересечения учитываются дважды: "
                "один раз как "
                "участники первой группы, "
                "второй — как "
                "участники второй. В "
                "объединении каждого нужно "
                "учесть ровно один "
                "раз. Поэтому из "
                "суммы вычитают численность пересечения. Получается "
                "|A ∪ B| = |A| + |B| − |A ∩ B|. "
                "Тот же принцип действует "
                "для вероятностей: вероятность объединения "
                "равна сумме вероятностей минус "
                "вероятность пересечения. Независимость для "
                "этого равенства не нужна. "
                "Если пересечение пусто, его вероятность нулевая, и формула превращается в "
                "обычное сложение несовместных событий."
            ), r"P(A\cup B)=P(A)+P(B)-P(A\cap B)"),
            _section("Два способа подсчёта", (
                "Можно сразу применить формулу "
                "объединения к численностям, "
                "а затем разделить "
                "на общее число "
                "участников. Можно сначала "
                "найти «только A» "
                "как |A| минус "
                "пересечение, аналогично «только "
                "B», затем сложить "
                "три непересекающиеся части. "
                "Второй способ длиннее, но полезен "
                "для проверки и для "
                "понимания условия. Равновероятный выбор "
                "участника даёт классическую вероятность "
                "как долю людей в "
                "объединении. Не делите на "
                "сумму двух названных групп: "
                "она может содержать повторы и вообще не описывает всё пространство выбора, где "
                "есть люди вне обеих групп."
            )),
            _section("Проверка согласованности данных", (
                "Число участников пересечения не "
                "может превышать численность "
                "ни одной из "
                "двух групп. После "
                "вычитания пересечения количества "
                "«только A» и "
                "«только B» должны "
                "быть неотрицательны. Объединение "
                "не может быть "
                "меньше каждой группы "
                "и не может превышать весь клуб. "
                "Оставшаяся часть — люди, "
                "не занимающиеся ни тем, "
                "ни другим. Четыре части "
                "вместе должны дать общее "
                "число участников. Это проверяет "
                "и математическую модель, и "
                "нормировку вероятностей. Если сумма вероятностей двух групп больше единицы, "
                "противоречия ещё нет: группы могут сильно пересекаться, поэтому необходимо "
                "правильно вычесть общую часть."
            )),
        ],
        "example": {
            "statement": (
                "Из 80 участников 37 играют в шахматы, 29 программируют, "
                "14 делают и то и другое. Одного участника выбирают равновероятно. "
                "Найдите вероятность, что у него есть хотя бы одно из этих занятий."
            ),
            "steps": [
                "Только шахматами занимаются 37 − 14 = 23, только программированием — 29 − 14 = "
                "15.",
                "Объединение содержит 23 + 15 + 14 = 52 человека.",
                "При равновероятном выборе P = 52/80 = 0,65.",
                "Вне двух групп 28 участников; четыре части 23, 15, 14 и 28 дают 80.",
            ],
            "answer": "0,65",
        },
        "takeaway": "При включающем «или» сложите две группы и один раз вычтите их пересечение.",
    },
    "total-probability-routing": {
        "sections": [
            _section("Разделение по происхождению", (
                "Вероятность свойства объекта может "
                "зависеть от того, "
                "из какой группы "
                "он пришёл. Заготовки "
                "в партии произведены "
                "двумя станками, и "
                "каждая относится ровно "
                "к одному из "
                "них. Группы происхождения "
                "несовместны и вместе "
                "охватывают всю партию. Их доли являются "
                "вероятностями выбора соответствующего происхождения "
                "при равновероятном выборе заготовки. "
                "Сумма долей должна быть "
                "единицей. Эти условия позволяют "
                "сначала вычислить вероятность брака "
                "по каждому пути происхождения, "
                "а затем сложить пути. Если были бы заготовки с третьего станка, его группу "
                "нельзя было бы молча игнорировать."
            )),
            _section("Условная доля брака — не доля всей партии", (
                "Вероятность брака среди продукции "
                "станка A означает "
                "P(D | A). Она "
                "относится только к "
                "этой группе, а "
                "не ко всем "
                "заготовкам. Чтобы получить "
                "вероятность пути «A "
                "и брак», умножьте "
                "долю A на "
                "условную вероятность брака в A. Это "
                "правило умножения для условных "
                "вероятностей, не предположение о "
                "независимости качества и происхождения. "
                "Наоборот, различие процентов брака "
                "показывает, почему зависимость нужно "
                "учесть. Точно так же "
                "строится путь через станок B. Каждое произведение относится уже ко всей партии "
                "и потому может быть сложено с другим."
            ), r"P(D)=P(A)P(D\mid A)+P(B)P(D\mid B)"),
            _section("Взвешенная сумма вместо среднего", (
                "После вычисления двух путей "
                "сложите их вероятности: "
                "заготовка не может "
                "одновременно происходить с "
                "обоих станков. Формула "
                "полной вероятности представляет "
                "собой взвешенное среднее "
                "двух условных вероятностей. "
                "Обычное арифметическое среднее "
                "подошло бы лишь "
                "при равных долях продукции. Чем больше "
                "группа, тем сильнее её "
                "качество влияет на общий "
                "результат. В таблице внимательно "
                "различайте колонку доли продукции "
                "и колонку вероятности брака "
                "внутри группы. Перемножать две "
                "вероятности брака между собой нет оснований: речь идёт об одной выбранной "
                "заготовке, а не о двух независимых дефектах."
            )),
            _section("Как контролировать результат", (
                "Общая вероятность брака лежит "
                "между вероятностями брака "
                "на двух станках, "
                "если их доли "
                "неотрицательны и дают "
                "единицу. Это сильная "
                "проверка: ответ вне "
                "этого промежутка указывает "
                "на ошибку весов "
                "или арифметики. Можно "
                "также вычислить вероятность годной заготовки "
                "по тем же двум "
                "путям и проверить сумму "
                "с вероятностью брака. Не "
                "путайте прямую задачу с "
                "обратной: если известно, что "
                "выбранная заготовка бракованная, вопрос "
                "о вероятности её происхождения потребует другой нормировки. Здесь сначала "
                "известны доли станков, а требуется свойство случайного изделия из всей партии."
            )),
        ],
        "example": {
            "statement": (
                "В партии продукция только двух станков: A дал 0,3 партии, B — 0,7. "
                "Вероятности брака внутри групп равны 0,02 и 0,06 соответственно. "
                "Заготовку равновероятно выбирают из всей партии. Найдите вероятность брака."
            ),
            "steps": [
                "Путь «A и брак» имеет вероятность 0,3 · 0,02 = 0,006.",
                "Путь «B и брак» имеет вероятность 0,7 · 0,06 = 0,042.",
                "Складываем несовместные пути: 0,006 + 0,042 = 0,048.",
                "Ответ лежит между 0,02 и 0,06 и ближе к 0,06, поскольку доля станка B больше.",
            ],
            "answer": "0,048",
        },
        "takeaway": (
            "Умножайте долю каждой группы на её условную вероятность, затем складывайте по всем "
            "группам."
        ),
    },
    "event-tree-exactly-one": {
        "sections": [
            _section("Зависимость задаётся отдельными ветвями", (
                "В двухэтапном испытании вероятность "
                "второго успеха может "
                "зависеть от результата "
                "первого. Поэтому вместо "
                "одного числа для "
                "второй попытки условие "
                "даёт два: после "
                "успеха и после "
                "неудачи. Обозначим вероятность "
                "первого успеха p, "
                "второго после успеха q, второго после "
                "неудачи r. Обе попытки "
                "выполняются обязательно, поэтому полные "
                "исходы имеют два результата. "
                "Нельзя прекращать дерево после "
                "первого успеха или считать "
                "два испытания независимыми по "
                "привычке. Разные условные вероятности — содержательная часть модели, и каждая "
                "должна оставаться на своей ветви."
            )),
            _section("Построение дерева", (
                "Из корня проведите две "
                "ветви: первый успех "
                "с вероятностью p "
                "и первая неудача "
                "с вероятностью 1 − p. "
                "После успеха подпишите "
                "вероятности второго успеха "
                "q и неудачи "
                "1 − q. После "
                "первой неудачи используйте "
                "r и 1 − r. В каждом "
                "узле исходящие вероятности дают "
                "единицу. Вероятность полного пути "
                "равна произведению вероятностей вдоль "
                "него. Это правило умножения "
                "с условием, поэтому оно "
                "применимо и при зависимости. "
                "Четыре листа дерева — успех–успех, успех–неудача, неудача–успех и "
                "неудача–неудача — несовместны и вместе описывают все возможные результаты двух "
                "попыток."
            ), r"P(\text{ровно один})=p(1-q)+(1-p)r"),
            _section("Выбор нужных листьев", (
                "Ровно один успех означает "
                "два подходящих пути: "
                "сначала успех, затем "
                "неудача; либо сначала "
                "неудача, затем успех. "
                "Их вероятности равны "
                "p(1 − q) и "
                "(1 − p)r. Поскольку "
                "эти пути несовместны, "
                "их вероятности складываются. "
                "Путь двух успехов не включается, хотя "
                "он подошёл бы для "
                "события «хотя бы один». "
                "Следите за порядком букв "
                "в произведениях: вероятность неудачи "
                "второй попытки после первого "
                "успеха равна 1 − q, "
                "а не 1 − r. Удобно обвести нужные листья на схеме до вычисления, чтобы "
                "арифметика соответствовала формулировке события."
            )),
            _section("Нормировка и сверка условий ветвей", (
                "Вычислите также два оставшихся "
                "пути: pq и "
                "(1 − p)(1 − r). "
                "Сумма всех четырёх "
                "вероятностей должна точно "
                "равняться единице. Ответ можно также проверить через дополнение: "
                "вычесть из единицы вероятности нулевого и двойного успеха. "
                "Нормировка служит проверкой полноты и числовой согласованности дерева. "
                "Правильность назначения условных вероятностей требует отдельной сверки. "
                "Перестановка q и r вместе с их дополнениями сохраняет сумму единицей "
                "и согласие двух способов вычисления, хотя ответ может оказаться неверным. "
                "Сверьте каждую ветвь с условием задачи: q — вероятность второго успеха "
                "после первого успеха, r — после первой неудачи. "
                "Если q и r "
                "совпали бы, второй успех "
                "не зависел бы от "
                "первого результата, и дерево "
                "упростилось бы до независимых "
                "попыток. Здесь условные ветви различаются специально: цель урока — научиться "
                "читать зависимость, а не автоматически повторять формулу для независимых "
                "событий."
            )),
        ],
        "example": {
            "statement": (
                "Первый успех имеет вероятность 0,6. Второй после успеха — 0,7, "
                "после неудачи — 0,2. Обе попытки выполняются обязательно. "
                "Найдите вероятность ровно одного успеха."
            ),
            "steps": [
                "Успех–неудача: 0,6 · (1 − 0,7) = 0,18.",
                "Неудача–успех: (1 − 0,6) · 0,2 = 0,08.",
                "Искомая вероятность равна 0,18 + 0,08 = 0,26.",
                "Два других пути дают 0,42 и 0,32. Сумма 0,18 + 0,08 + 0,42 + 0,32 = 1.",
            ],
            "answer": "0,26",
        },
        "takeaway": (
            "На каждой ветви используйте своё условие; умножайте вдоль пути и складывайте "
            "подходящие несовместные пути."
        ),
    },
    "combinatorial-subset": {
        "sections": [
            _section("Порядок выбора определяет исход", (
                "Две карточки выбирают одновременно, "
                "поэтому результатом является "
                "неупорядоченная пара. Пара "
                "из карточек A "
                "и B совпадает "
                "с парой из "
                "B и A. "
                "Все карточки различны, "
                "и одна карточка "
                "не может входить "
                "в пару дважды. Условие о равновероятности "
                "всех пар позволяет использовать "
                "классическую формулу вероятности после "
                "комбинаторного подсчёта. Сами категории "
                "«две отмеченные», «одна отмеченная» "
                "и «ни одной» "
                "обычно не равновероятны: за "
                "ними стоит разное число конкретных пар. Поэтому число названных типов "
                "результатов не подходит в качестве знаменателя."
            )),
            _section("Как получить число сочетаний", (
                "Для упорядоченного выбора первой "
                "и второй различных "
                "карточек имеется N "
                "вариантов первого места "
                "и N − 1 "
                "второго. Произведение N(N − 1) "
                "считает каждую неупорядоченную "
                "пару дважды: в "
                "двух возможных порядках. "
                "Разделив на два, "
                "получаем число сочетаний C(N, 2). Если "
                "отмеченных карточек m, подходящих "
                "пар C(m, 2) = m(m − 1)/2. "
                "При m = 1 это "
                "число нулевое: выбрать две "
                "различные отмеченные невозможно. Нулевая "
                "вероятность такого события корректна "
                "и не означает, что исходное испытание невозможно. Общий набор по-прежнему "
                "содержит достаточно разных карточек для выбора пары."
            ), r"P=\frac{\binom m2}{\binom N2}=\frac{m(m-1)}{N(N-1)}"),
            _section("Одинаковая модель в числителе и знаменателе", (
                "Разделите число подходящих пар "
                "на число всех "
                "пар. Можно считать "
                "обе величины неупорядоченными "
                "или обе упорядоченными: "
                "общий множитель два "
                "сократится. Нельзя считать "
                "числитель одним способом, "
                "а знаменатель другим, "
                "иначе вероятность изменится "
                "вдвое. Другая проверка — представить "
                "последовательный выбор без возвращения: "
                "m/N на первом шаге "
                "и (m − 1)/(N − 1) "
                "на втором при первом "
                "отмеченном. Произведение совпадает "
                "с отношением сочетаний. Совпадение "
                "объясняется эквивалентностью двух моделей равномерного выбора пары, а не "
                "независимостью шагов: без возвращения второй шаг зависит от первого."
            )),
            _section("Проверки полноты и крайних случаев", (
                "Если отмечены все карточки, "
                "любая пара подходит "
                "и вероятность равна "
                "единице. Если отмеченных "
                "меньше двух, вероятность "
                "нулевая. Между этими "
                "случаями увеличение числа "
                "отмеченных должно увеличивать "
                "ответ. Для полной "
                "проверки можно разбить "
                "пары на две отмеченные, смешанные "
                "и две неотмеченные. Их "
                "количества соответственно C(m, 2), "
                "m(N − m) и C(N − m, 2). "
                "Сумма должна дать C(N, 2). "
                "Так проверяется нормировка по "
                "всем типам пар. Сокращайте "
                "дробь до десятичной записи. В заданиях этой серии параметры подобраны для "
                "точного конечного ответа; округление не заменяет комбинаторный подсчёт."
            )),
        ],
        "example": {
            "statement": (
                "Из 10 разных карточек 9 отмечены. Все пары различных карточек равновероятны. "
                "Найдите вероятность выбрать две отмеченные."
            ),
            "steps": [
                "Всего неупорядоченных пар 10 · 9 / 2 = 45.",
                "Подходящих пар 9 · 8 / 2 = 36, поэтому P = 36/45 = 0,8.",
                "Проверка последовательным выбором: (9/10) · (8/9) = 0,8.",
                "Остальные девять пар содержат единственную неотмеченную карточку; 36 + 9 = 45.",
            ],
            "answer": "0,8",
        },
        "takeaway": (
            "Определите, важен ли порядок, и считайте благоприятные и все исходы в одной "
            "комбинаторной модели."
        ),
    },
})
