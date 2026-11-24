// SPDX-License-Identifier: GPL-2.0-only
/*
 * Allwinner T527 / sun55i (sunxi-pwm-v201) hardware PWM driver for Linux 6.18+
 *
 * Register layout derived from Allwinner sunxi-pwm-v201 (T527 / sun55iw3).
 */

#include <linux/clk.h>
#include <linux/delay.h>
#include <linux/err.h>
#include <linux/io.h>
#include <linux/iopoll.h>
#include <linux/math64.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/platform_device.h>
#include <linux/pwm.h>
#include <linux/reset.h>
#include <linux/spinlock.h>

#define PWM_PCCR_BASE		0x0020
#define PWM_PCCR(ch)		(PWM_PCCR_BASE + (((ch) >> 1) * 4))
#define PWM_PCCR_CLK_SRC_SHIFT	7
#define PWM_PCCR_CLK_SRC_MASK	GENMASK(8, 7)
#define PWM_PCCR_DIV_M_MASK	GENMASK(3, 0)

#define PWM_PCGR		0x0040
#define PWM_PER			0x0080

#define PWM_PCR_BASE		0x0100
#define PWM_PPR_BASE		0x0104
#define PWM_CH_STRIDE		0x0020
#define PWM_PCR(ch)		(PWM_PCR_BASE + (ch) * PWM_CH_STRIDE)
#define PWM_PPR(ch)		(PWM_PPR_BASE + (ch) * PWM_CH_STRIDE)

#define PWM_PCR_PRESCAL_MASK	GENMASK(7, 0)
#define PWM_PCR_ACT_STA		BIT(8)
#define PWM_PCR_MODE_MASK	GENMASK(10, 9)
#define PWM_PCR_PERIOD_RDY	BIT(11)

#define PWM_PPR_ACT_MASK	GENMASK(15, 0)
#define PWM_PPR_ENTIRE_SHIFT	16
#define PWM_PPR_ENTIRE_MASK	GENMASK(31, 16)

#define PWM_MAX_CHANNELS	16
#define PWM_MAX_DIV_M_POW	8
#define PWM_MAX_PRESCAL		255U
#define PWM_MAX_CYCLES		65535U

struct sun55i_pwm_chip {
	void __iomem *base;
	struct clk *bus_clk;
	struct clk *hosc_clk;
	struct clk *apb_clk;
	struct reset_control *rst;
	u64 hosc_rate;
	u64 apb_rate;
	spinlock_t lock;
};

static inline u32 sun55i_pwm_readl(struct sun55i_pwm_chip *sunxi, u32 offset)
{
	return readl(sunxi->base + offset);
}

static inline void sun55i_pwm_writel(struct sun55i_pwm_chip *sunxi, u32 offset, u32 val)
{
	writel(val, sunxi->base + offset);
}

static int sun55i_pwm_calc_params(u64 clk_rate, u64 period_ns, u64 duty_ns,
				  u32 *div_m_pow, u32 *prescale,
				  u32 *entire_cycles, u32 *active_cycles)
{
	u64 total_beats;
	u32 m, k;

	if (!clk_rate || !period_ns)
		return -EINVAL;

	total_beats = mul_u64_u64_div_u64(clk_rate, period_ns, NSEC_PER_SEC);
	if (total_beats == 0)
		total_beats = 1;

	for (m = 0; m <= PWM_MAX_DIV_M_POW; m++) {
		u64 div_beats = total_beats >> m;

		if (div_beats == 0)
			div_beats = 1;

		for (k = 0; k <= PWM_MAX_PRESCAL; k++) {
			u64 cycles = div64_u64(div_beats, k + 1);

			if (cycles <= PWM_MAX_CYCLES) {
				u64 act;

				if (cycles == 0)
					cycles = 1;

				act = mul_u64_u64_div_u64(cycles, duty_ns, period_ns);
				if (act > cycles)
					act = cycles;

				*div_m_pow = m;
				*prescale = k;
				*entire_cycles = (u32)cycles;
				*active_cycles = (u32)act;
				return 0;
			}
		}
	}

	return -EINVAL;
}

static int sun55i_pwm_apply(struct pwm_chip *chip, struct pwm_device *pwm,
			    const struct pwm_state *state)
{
	struct sun55i_pwm_chip *sunxi = pwmchip_get_drvdata(chip);
	u32 ch = pwm->hwpwm;
	u32 div_m_pow = 0, prescale = 0, entire_cycles = 1, active_cycles = 0;
	u32 pccr, pcr, ppr, reg_val;
	u32 clk_src = 0;
	u64 clk_rate;
	unsigned long flags;
	int ret;

	if (!state->enabled) {
		spin_lock_irqsave(&sunxi->lock, flags);
		reg_val = sun55i_pwm_readl(sunxi, PWM_PER);
		reg_val &= ~BIT(ch);
		sun55i_pwm_writel(sunxi, PWM_PER, reg_val);

		reg_val = sun55i_pwm_readl(sunxi, PWM_PCGR);
		reg_val &= ~BIT(ch);
		sun55i_pwm_writel(sunxi, PWM_PCGR, reg_val);
		spin_unlock_irqrestore(&sunxi->lock, flags);
		return 0;
	}

	if (state->period <= 334 && sunxi->apb_rate > sunxi->hosc_rate) {
		clk_src = 1;
		clk_rate = sunxi->apb_rate;
	} else {
		clk_src = 0;
		clk_rate = sunxi->hosc_rate;
	}

	ret = sun55i_pwm_calc_params(clk_rate, state->period, state->duty_cycle,
				     &div_m_pow, &prescale,
				     &entire_cycles, &active_cycles);
	if (ret)
		return ret;

	spin_lock_irqsave(&sunxi->lock, flags);

	/* Ensure bypass bit for this channel is cleared */
	reg_val = sun55i_pwm_readl(sunxi, PWM_PCGR);
	reg_val &= ~BIT(16 + ch);
	sun55i_pwm_writel(sunxi, PWM_PCGR, reg_val);

	/* Configure clock source and pre-divider M (shared register per pair) */
	pccr = sun55i_pwm_readl(sunxi, PWM_PCCR(ch));
	pccr &= ~(PWM_PCCR_CLK_SRC_MASK | PWM_PCCR_DIV_M_MASK);
	pccr |= (clk_src << PWM_PCCR_CLK_SRC_SHIFT) | (div_m_pow & PWM_PCCR_DIV_M_MASK);
	sun55i_pwm_writel(sunxi, PWM_PCCR(ch), pccr);

	/* Configure prescaler K, cycle mode, and active polarity */
	pcr = sun55i_pwm_readl(sunxi, PWM_PCR(ch));
	pcr &= ~(PWM_PCR_PRESCAL_MASK | PWM_PCR_ACT_STA | PWM_PCR_MODE_MASK);
	pcr |= prescale & PWM_PCR_PRESCAL_MASK;
	if (state->polarity == PWM_POLARITY_NORMAL)
		pcr |= PWM_PCR_ACT_STA;
	sun55i_pwm_writel(sunxi, PWM_PCR(ch), pcr);

	/* Wait briefly for PERIOD_RDY == 0 before writing PPR */
	readl_poll_timeout_atomic(sunxi->base + PWM_PCR(ch), reg_val,
				  !(reg_val & PWM_PCR_PERIOD_RDY), 1, 100);

	ppr = ((entire_cycles - 1) << PWM_PPR_ENTIRE_SHIFT) & PWM_PPR_ENTIRE_MASK;
	ppr |= active_cycles & PWM_PPR_ACT_MASK;
	sun55i_pwm_writel(sunxi, PWM_PPR(ch), ppr);

	/* Ungate channel clock and enable channel */
	reg_val = sun55i_pwm_readl(sunxi, PWM_PCGR);
	reg_val |= BIT(ch);
	sun55i_pwm_writel(sunxi, PWM_PCGR, reg_val);

	reg_val = sun55i_pwm_readl(sunxi, PWM_PER);
	reg_val |= BIT(ch);
	sun55i_pwm_writel(sunxi, PWM_PER, reg_val);

	spin_unlock_irqrestore(&sunxi->lock, flags);
	return 0;
}

static int sun55i_pwm_get_state(struct pwm_chip *chip, struct pwm_device *pwm,
				struct pwm_state *state)
{
	struct sun55i_pwm_chip *sunxi = pwmchip_get_drvdata(chip);
	u32 ch = pwm->hwpwm;
	u32 pccr, pcr, ppr, per;
	u32 clk_src, div_m, prescale, entire_cycles, active_cycles;
	u64 clk_rate, eff_rate;
	unsigned long flags;

	spin_lock_irqsave(&sunxi->lock, flags);
	per = sun55i_pwm_readl(sunxi, PWM_PER);
	pccr = sun55i_pwm_readl(sunxi, PWM_PCCR(ch));
	pcr = sun55i_pwm_readl(sunxi, PWM_PCR(ch));
	ppr = sun55i_pwm_readl(sunxi, PWM_PPR(ch));
	spin_unlock_irqrestore(&sunxi->lock, flags);

	state->enabled = !!(per & BIT(ch));
	state->polarity = (pcr & PWM_PCR_ACT_STA) ?
			  PWM_POLARITY_NORMAL : PWM_POLARITY_INVERSED;

	clk_src = (pccr & PWM_PCCR_CLK_SRC_MASK) >> PWM_PCCR_CLK_SRC_SHIFT;
	div_m = 1U << (pccr & PWM_PCCR_DIV_M_MASK);
	prescale = (pcr & PWM_PCR_PRESCAL_MASK) + 1U;

	clk_rate = (clk_src == 1 && sunxi->apb_rate) ? sunxi->apb_rate : sunxi->hosc_rate;
	eff_rate = div64_u64(clk_rate, (u64)div_m * prescale);
	if (!eff_rate)
		eff_rate = 1;

	entire_cycles = ((ppr & PWM_PPR_ENTIRE_MASK) >> PWM_PPR_ENTIRE_SHIFT) + 1U;
	active_cycles = ppr & PWM_PPR_ACT_MASK;

	state->period = DIV64_U64_ROUND_UP((u64)entire_cycles * NSEC_PER_SEC, eff_rate);
	state->duty_cycle = DIV64_U64_ROUND_UP((u64)active_cycles * NSEC_PER_SEC, eff_rate);

	return 0;
}

static const struct pwm_ops sun55i_pwm_ops = {
	.apply = sun55i_pwm_apply,
	.get_state = sun55i_pwm_get_state,
};

static void sun55i_pwm_cleanup(void *data)
{
	struct sun55i_pwm_chip *sunxi = data;

	clk_disable_unprepare(sunxi->apb_clk);
	clk_disable_unprepare(sunxi->hosc_clk);
	clk_disable_unprepare(sunxi->bus_clk);
	reset_control_assert(sunxi->rst);
}

static int sun55i_pwm_probe(struct platform_device *pdev)
{
	struct device *dev = &pdev->dev;
	struct pwm_chip *chip;
	struct sun55i_pwm_chip *sunxi;
	u32 npwm = PWM_MAX_CHANNELS;
	int ret;

	of_property_read_u32(dev->of_node, "sunxi,pwm-channels", &npwm);
	if (npwm == 0 || npwm > PWM_MAX_CHANNELS)
		return -EINVAL;

	chip = devm_pwmchip_alloc(dev, npwm, sizeof(*sunxi));
	if (IS_ERR(chip))
		return PTR_ERR(chip);

	sunxi = pwmchip_get_drvdata(chip);
	spin_lock_init(&sunxi->lock);

	sunxi->base = devm_platform_ioremap_resource(pdev, 0);
	if (IS_ERR(sunxi->base))
		return PTR_ERR(sunxi->base);

	sunxi->rst = devm_reset_control_get_exclusive(dev, NULL);
	if (IS_ERR(sunxi->rst))
		return dev_err_probe(dev, PTR_ERR(sunxi->rst), "failed to get reset\n");

	sunxi->bus_clk = devm_clk_get(dev, "bus");
	if (IS_ERR(sunxi->bus_clk))
		return dev_err_probe(dev, PTR_ERR(sunxi->bus_clk), "failed to get bus clock\n");

	sunxi->hosc_clk = devm_clk_get_optional(dev, "hosc");
	if (IS_ERR(sunxi->hosc_clk))
		return dev_err_probe(dev, PTR_ERR(sunxi->hosc_clk), "failed to get hosc clock\n");

	sunxi->apb_clk = devm_clk_get_optional(dev, "apb");
	if (IS_ERR(sunxi->apb_clk))
		return dev_err_probe(dev, PTR_ERR(sunxi->apb_clk), "failed to get apb clock\n");

	ret = reset_control_deassert(sunxi->rst);
	if (ret)
		return dev_err_probe(dev, ret, "failed to deassert reset\n");

	ret = clk_prepare_enable(sunxi->bus_clk);
	if (ret) {
		reset_control_assert(sunxi->rst);
		return dev_err_probe(dev, ret, "failed to enable bus clock\n");
	}

	ret = clk_prepare_enable(sunxi->hosc_clk);
	if (ret) {
		clk_disable_unprepare(sunxi->bus_clk);
		reset_control_assert(sunxi->rst);
		return dev_err_probe(dev, ret, "failed to enable hosc clock\n");
	}

	ret = clk_prepare_enable(sunxi->apb_clk);
	if (ret) {
		clk_disable_unprepare(sunxi->hosc_clk);
		clk_disable_unprepare(sunxi->bus_clk);
		reset_control_assert(sunxi->rst);
		return dev_err_probe(dev, ret, "failed to enable apb clock\n");
	}

	ret = devm_add_action_or_reset(dev, sun55i_pwm_cleanup, sunxi);
	if (ret)
		return ret;

	sunxi->hosc_rate = sunxi->hosc_clk ? clk_get_rate(sunxi->hosc_clk) : 24000000ULL;
	if (!sunxi->hosc_rate)
		sunxi->hosc_rate = 24000000ULL;

	sunxi->apb_rate = sunxi->apb_clk ? clk_get_rate(sunxi->apb_clk) : 0;

	chip->ops = &sun55i_pwm_ops;

	ret = devm_pwmchip_add(dev, chip);
	if (ret)
		return dev_err_probe(dev, ret, "failed to register pwmchip\n");

	dev_info(dev, "sun55i-t527 hardware PWM registered (%u channels, hosc=%llu Hz)\n",
		 npwm, sunxi->hosc_rate);
	return 0;
}

static const struct of_device_id sun55i_pwm_of_match[] = {
	{ .compatible = "allwinner,sun55i-t527-pwm" },
	{ .compatible = "allwinner,sunxi-pwm-v201" },
	{ /* sentinel */ }
};
MODULE_DEVICE_TABLE(of, sun55i_pwm_of_match);

static struct platform_driver sun55i_pwm_driver = {
	.probe = sun55i_pwm_probe,
	.driver = {
		.name = "pwm-sun55i-t527",
		.of_match_table = sun55i_pwm_of_match,
	},
};
module_platform_driver(sun55i_pwm_driver);

MODULE_DESCRIPTION("Allwinner T527 / sun55i hardware PWM driver");
MODULE_AUTHOR("ukhan / Orange Pi 4A");
MODULE_LICENSE("GPL");
